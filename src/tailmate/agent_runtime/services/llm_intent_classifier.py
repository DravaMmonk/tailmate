"""Gemini-backed intent classifier with structured JSON output."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import time
from threading import Lock
from typing import Any, Callable

from google.auth.credentials import Credentials
import vertexai
from vertexai.generative_models import GenerationConfig, GenerativeModel

from tailmate.agent_runtime.pipeline.turn_context import IntentClassification, TurnContext
from tailmate.agent_runtime.ports.skill_registry import SkillRegistry
from tailmate.agent_runtime.pipeline.skills._shared import (
    resolve_active_dog_id,
    resolve_active_dog_name,
)
from tailmate.contracts.errors import AdapterError
from tailmate.metrics import record_llm_latency


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", stripped)
        stripped = re.sub(r"\n?```\s*$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or start > end:
        raise ValueError("No JSON object found in model response.")
    return json.loads(stripped[start : end + 1])


def _clamp_confidence(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(max(numeric, 0.0), 1.0)


@dataclass
class LLMIntentClassifier:
    """Use Gemini to classify the current turn into runtime skills."""

    skill_registry: SkillRegistry
    model_name: str
    project_id: str
    location: str
    dog_profile_db_adapter: Any | None = None
    api_key: str | None = None
    credentials: Credentials | None = None
    timeout_seconds: int = 15
    initializer: Callable[..., None] = vertexai.init
    model_factory: Callable[[str], Any] = GenerativeModel
    _model: Any | None = field(default=None, init=False, repr=False)
    _init_lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def classify(self, ctx: TurnContext) -> IntentClassification:
        started_at = time.perf_counter()
        try:
            response = self._ensure_model().generate_content(
                self._build_prompt(ctx),
                generation_config=GenerationConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
                request_options={"timeout": self.timeout_seconds},
            )
        except Exception as exc:
            raise AdapterError(
                f"Failed to reach Gemini model '{self.model_name}' for intent classification."
            ) from exc
        finally:
            record_llm_latency(
                model=self.model_name,
                latency_seconds=time.perf_counter() - started_at,
            )

        response_text = str(getattr(response, "text", "") or "").strip()
        if not response_text:
            raise AdapterError("Gemini returned an empty intent-classification payload.")

        try:
            payload = _extract_json_object(response_text)
        except Exception as exc:
            raise AdapterError("Gemini returned an invalid intent-classification payload.") from exc

        return self._parse_payload(payload)

    def _build_prompt(self, ctx: TurnContext) -> str:
        recent_turns = tuple(ctx.session.turns[:-1][-2:])
        active_dog_id = resolve_active_dog_id(ctx.session, ctx.request_metadata)
        active_dog_name = resolve_active_dog_name(
            ctx.session,
            ctx.request_metadata,
            self.dog_profile_db_adapter,
        )
        available_skills = [
            {
                "skill_id": skill.skill_id,
                "routing_description": skill.routing_description,
            }
            for skill in self._routable_skills()
        ]
        session_context = {
            "active_dog": {
                "dog_id": active_dog_id,
                "dog_name": active_dog_name,
            }
            if active_dog_id or active_dog_name
            else None,
            "locale": ctx.locale,
            "recent_turns": recent_turns,
        }
        return (
            "You are a routing classifier for a dog care assistant.\n"  # nosec B608
            "Select which runtime skills should handle the user message.\n"
            "Return JSON only.\n"
            "Rules:\n"
            "- Use only skill ids from the provided list.\n"
            "- Use intent 'known' when one or more concrete product skills should execute.\n"
            "- Use intent 'open' for broad dog-care questions or when only knowledge-base style help applies.\n"
            "- Prefer 'dog_profile:recall' for questions asking about stored facts for the active dog.\n"
            "- Prefer 'dog_profile:create' only when the user is introducing a dog and there is no active dog.\n"
            "- Prefer 'dog_profile:enrich' when the user adds or updates facts about the active dog.\n"
            "- Prefer 'dog_profile:enrich' for declarative statements about the active dog "
            "(eating habits, preferences, likes, dislikes, behaviours) even without a question mark.\n"
            "- When the user explicitly asks to save, record, or remember something about their dog, "
            "always use 'dog_profile:enrich' regardless of message length.\n"
            "- Include 'knowledge_base' when the message is a dog-care question that needs general guidance.\n"
            "- Keep reasoning to one sentence.\n"
            "Available skills:\n"
            f"{json.dumps(available_skills, ensure_ascii=False)}\n"
            "Session context:\n"
            f"{json.dumps(session_context, ensure_ascii=False)}\n"
            f"User message: {json.dumps(ctx.message, ensure_ascii=False)}\n"
            "Response schema:\n"
            '{"matched_skills":["skill_id"],"intent":"known","confidence":0.0,"reasoning":"one sentence"}'
        )

    def _parse_payload(self, payload: dict[str, Any]) -> IntentClassification:
        intent = str(payload.get("intent", "")).strip()
        if intent not in {"known", "open"}:
            raise AdapterError("Gemini returned an invalid intent value.")

        routable_skill_ids = {skill.skill_id for skill in self._routable_skills()}
        raw_skills = payload.get("matched_skills")
        if not isinstance(raw_skills, list):
            raise AdapterError("Gemini returned invalid matched_skills.")
        unique_skills: list[str] = []
        for raw_skill in raw_skills:
            skill_id = str(raw_skill).strip()
            if skill_id not in routable_skill_ids:
                continue
            if skill_id in unique_skills:
                continue
            unique_skills.append(skill_id)
        matched_skills = tuple(unique_skills)
        if intent == "known" and not matched_skills:
            intent = "open"
        if intent == "open" and "knowledge_base" in routable_skill_ids and "knowledge_base" not in matched_skills:
            matched_skills = matched_skills + ("knowledge_base",)
        confidence = _clamp_confidence(payload.get("confidence"))
        reasoning = str(payload.get("reasoning", "")).strip() or None
        return IntentClassification(
            intent=intent,
            matched_skills=matched_skills,
            confidence=confidence,
            reasoning=reasoning,
        )

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._init_lock:
            if self._model is None:
                self.initializer(
                    project=self.project_id,
                    location=self.location,
                    credentials=self.credentials,
                    api_key=self.api_key,
                )
                self._model = self.model_factory(self.model_name)
        return self._model

    def _routable_skills(self) -> tuple[Any, ...]:
        return tuple(
            skill
            for skill in self.skill_registry.skills()
            if skill.routing_description
        )
