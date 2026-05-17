"""Graph orchestration service."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
import time
from typing import Any

from tailmate.agent_runtime.current_context import get_current_context
from tailmate.agent_runtime.models.session_context import SessionContext
from tailmate.agent_runtime.pipeline.skills._shared import (
    list_known_dog_profiles,
    resolve_active_dog_name,
)
from tailmate.agent_runtime.pipeline.steps._tool_finder import find_tool
from tailmate.agent_runtime.ports.conversational_responder import ConversationalResponder
from tailmate.agent_runtime.ports.intent_classifier import IntentClassifier
from tailmate.agent_runtime.pipeline.skills import register_standard_runtime_skills
from tailmate.agent_runtime.pipeline.steps.dog_context_step import DogContextStep
from tailmate.agent_runtime.pipeline.steps.intent_classifier_step import IntentClassifierStep
from tailmate.agent_runtime.pipeline.steps.profile_recall_step import ProfileRecallStep
from tailmate.agent_runtime.pipeline.steps.response_assembly_step import ResponseAssemblyStep
from tailmate.agent_runtime.pipeline.steps.skill_execution_step import SkillExecutionStep
from tailmate.agent_runtime.pipeline.turn_context import SkillExecutionResult, TurnContext
from tailmate.agent_runtime.pipeline.turn_pipeline import TurnPipeline
from tailmate.agent_runtime.ports.dog_profile_db_adapter import DogProfileDBAdapter
from tailmate.agent_runtime.ports.knowledge_retriever import KnowledgeRetriever
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.agent_runtime.ports.session_store import SessionStore
from tailmate.agent_runtime.ports.skill_registry import SkillRegistry
from tailmate.agent_runtime.services.turn_messages import (
    build_active_dog_selection_prompt,
    PREFERRED_LOCALE_ATTRIBUTE,
    build_fallback_message,
    build_session_welcome,
    resolve_locale,
)
from tailmate.contracts.constants import (
    DOG_PROFILE_RESULT_METADATA_KEY,
    PREFERRED_LOCALE_ATTRIBUTE_KEY,
    STRIP_METADATA_REQUEST_METADATA_KEY,
    STRIP_METADATA_RESULT_METADATA_KEY,
    STRIP_METADATA_TOOL_ID,
    TURN_DEBUG_METADATA_KEY,
)
from tailmate.contracts.errors import DomainError, TailmateError, InternalError, SkillRegistrationError
from tailmate.contracts.types import extract_strip_metadata_request
from tailmate.metrics import record_session_started

# Re-export so existing imports of DogProfileTurnResult from this module keep working.
from tailmate.agent_runtime.pipeline.turn_context import DogProfileTurnResult as DogProfileTurnResult  # noqa: F401


@dataclass
class GraphOrchestrator:
    """Owns runtime flow and persisted state transitions.

    Routing logic is delegated to a ``TurnPipeline`` assembled from discrete
    ``RoutingStep`` implementations.  The constructor signature is unchanged so
    existing call-sites and tests require no modification.
    """

    session_store: SessionStore
    skill_registry: SkillRegistry
    observability: Observability
    intent_classifier: IntentClassifier
    dog_profile_db_adapter: DogProfileDBAdapter | None = None
    knowledge_retriever: KnowledgeRetriever | None = None
    conversational_responder: ConversationalResponder | None = None

    _pipeline: TurnPipeline = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if hasattr(self.skill_registry, "register_runtime_skill"):
            register_standard_runtime_skills(
                self.skill_registry,
                dog_profile_db_adapter=self.dog_profile_db_adapter,
                knowledge_retriever=self.knowledge_retriever,
                observability=self.observability,
                conversational_responder_available=self.conversational_responder is not None,
            )
        self._pipeline = TurnPipeline(
            steps=[
                IntentClassifierStep(self.intent_classifier),
                DogContextStep(self.dog_profile_db_adapter, self.observability),
                SkillExecutionStep(
                    self.skill_registry,
                    self.observability,
                    self.dog_profile_db_adapter,
                    self.knowledge_retriever,
                ),
                ProfileRecallStep(self.dog_profile_db_adapter, self.observability),
                ResponseAssemblyStep(
                    self.skill_registry,
                    self.conversational_responder,
                    self.observability,
                ),
            ]
        )

    @dataclass(frozen=True)
    class PreparedAudioUpload:
        """Sanitized audio upload plus the optional routing transcript."""

        strip_result: dict[str, Any]
        transcription_text: str | None

    def run(self, session_id: str, message: str) -> SessionContext:
        """Execute one conversation turn and return the updated session context."""

        started_at = time.perf_counter()

        # ── Setup ────────────────────────────────────────────────────────
        context = self.session_store.load(session_id)
        request_context = get_current_context()
        request_metadata = dict(request_context.metadata) if request_context is not None else {}

        try:
            strip_request = extract_strip_metadata_request(request_metadata)
        except ValueError as exc:
            raise DomainError("Invalid strip_metadata_request metadata.") from exc

        audio_upload: GraphOrchestrator.PreparedAudioUpload | None = None
        original_message = message
        if self._is_audio_strip_request(strip_request):
            audio_upload = self._prepare_audio_message(session_id, strip_request)
            context.attributes[STRIP_METADATA_RESULT_METADATA_KEY] = dict(audio_upload.strip_result)
            if audio_upload.transcription_text is not None:
                message = audio_upload.transcription_text
            strip_request = None

        locale_resolution = resolve_locale(
            message=message,
            request_metadata=request_metadata,
            context_attributes=context.attributes,
        )
        if locale_resolution.source == "metadata":
            context.attributes[PREFERRED_LOCALE_ATTRIBUTE_KEY] = locale_resolution.locale
        elif (
            locale_resolution.source == "context"
            and PREFERRED_LOCALE_ATTRIBUTE not in context.attributes
        ):
            context.attributes[PREFERRED_LOCALE_ATTRIBUTE_KEY] = locale_resolution.locale

        if audio_upload is not None:
            self._record_strip_metadata_result(
                session_id=session_id,
                locale=locale_resolution.locale,
                strip_result=audio_upload.strip_result,
            )
            if audio_upload.transcription_text is None:
                return self._complete_precomputed_strip_metadata_turn(
                    context,
                    session_id=session_id,
                    message=original_message,
                    locale_resolution=locale_resolution,
                    request_metadata=request_metadata,
                    strip_result=audio_upload.strip_result,
                    started_at=started_at,
                )

        is_new_session = len(context.turns) == 0
        if is_new_session:
            channel = str(request_metadata.get("channel", "direct")).strip() or "direct"
            record_session_started(channel=channel)
        if is_new_session and not message.strip() and strip_request is None:
            known_profiles = list_known_dog_profiles(
                request_metadata,
                self.dog_profile_db_adapter,
            )
            returning_dog_name = resolve_active_dog_name(
                context,
                request_metadata,
                self.dog_profile_db_adapter,
            )
            if returning_dog_name is None and len(known_profiles) == 1:
                returning_dog_name = str(known_profiles[0].name).strip() or None
            if returning_dog_name is not None:
                welcome_message = build_fallback_message(
                    locale=locale_resolution.locale,
                    reason="fallback.greeting",
                    dog_name=returning_dog_name,
                )
            elif len(known_profiles) > 1:
                welcome_message = build_active_dog_selection_prompt(
                    locale=locale_resolution.locale,
                    dog_names=tuple(
                        str(profile.name).strip()
                        for profile in known_profiles
                        if str(profile.name).strip()
                    ),
                )
            else:
                welcome_message = build_session_welcome(locale=locale_resolution.locale)
            turn_debug: dict[str, Any] = {
                "intent": None,
                "matched_skills": [],
                "intent_confidence": None,
                "intent_reasoning": None,
                "source": "welcome",
                "response_key": welcome_message.key,
                "response_provenance": "deterministic",
                "locale": locale_resolution.locale,
                "locale_source": locale_resolution.source,
                "requested_locale": locale_resolution.requested_locale,
                "locale_fallback_reason": locale_resolution.locale_fallback_reason,
                "fallback_reason": None,
                "skill_attempted": [],
                "skill_error": None,
                "updated_fields": [],
                "raw_note_saved": False,
                "safety_boundary_hit": False,
            }
            context.attributes["last_response"] = welcome_message.text
            context.attributes[TURN_DEBUG_METADATA_KEY] = turn_debug
            context.turns.append(
                {
                    "role": "assistant",
                    "message": welcome_message.text,
                    "source": "welcome",
                    "locale": locale_resolution.locale,
                    "response_key": welcome_message.key,
                    "response_provenance": "deterministic",
                    "fallback_reason": None,
                }
            )
            self.observability.info(
                "orchestrator_welcome",
                session_id=session_id,
                locale=locale_resolution.locale,
                locale_source=locale_resolution.source,
                locale_fallback_reason=locale_resolution.locale_fallback_reason,
                requested_locale=locale_resolution.requested_locale,
                response_key=welcome_message.key,
                latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
            self.observability.info(
                "orchestrator_run",
                session_id=session_id,
                intent=None,
                skill=None,
                latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
            try:
                self.session_store.save(context)
            except Exception as exc:
                self.observability.info(
                    "orchestrator_session_save_failed",
                    session_id=session_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            return context

        context.turns.append({"role": "user", "message": message})

        # ── Pipeline ─────────────────────────────────────────────────────
        ctx = TurnContext(
            session=context,
            session_id=session_id,
            message=message,
            locale=locale_resolution.locale,
            locale_resolution=locale_resolution,
            request_metadata=request_metadata,
            strip_request=strip_request,
        )
        self._pipeline.execute(ctx)

        return self._finalize_context(
            context,
            ctx,
            locale_resolution=locale_resolution,
            started_at=started_at,
        )

    def _finalize_context(
        self,
        context: SessionContext,
        ctx: TurnContext,
        *,
        locale_resolution: Any,
        started_at: float,
    ) -> SessionContext:
        """Persist the assembled assistant turn and emit top-level observability."""

        assistant_turn = ctx.assistant_turn
        assistant_message = assistant_turn.message if assistant_turn is not None else ""
        response_key = assistant_turn.response_key if assistant_turn is not None else None

        turn_debug: dict[str, Any] = {
            "intent": ctx.intent.intent if ctx.intent is not None else None,
            "matched_skills": list(ctx.intent.matched_skills) if ctx.intent is not None else [],
            "intent_confidence": ctx.intent.confidence if ctx.intent is not None else None,
            "intent_reasoning": ctx.intent.reasoning if ctx.intent is not None else None,
            "source": assistant_turn.source if assistant_turn is not None else ctx.source,
            "response_key": response_key,
            "response_provenance": (
                assistant_turn.response_provenance if assistant_turn is not None else None
            ),
            "locale": locale_resolution.locale,
            "locale_source": locale_resolution.source,
            "requested_locale": locale_resolution.requested_locale,
            "locale_fallback_reason": locale_resolution.locale_fallback_reason,
            "fallback_reason": (
                assistant_turn.fallback_reason if assistant_turn is not None else ctx.fallback_reason
            ),
            "skill_attempted": ctx.skill_attempted,
            "skill_error": ctx.skill_error,
            "updated_fields": ctx.updated_fields,
            "raw_note_saved": ctx.raw_note_saved,
            "safety_boundary_hit": ctx.safety_boundary_hit,
        }

        context.attributes["last_response"] = assistant_message
        context.attributes[TURN_DEBUG_METADATA_KEY] = turn_debug
        context.turns.append(
            {
                "role": "assistant",
                "message": assistant_message,
                "skill_id": assistant_turn.skill_id if assistant_turn is not None else ctx.skill_id,
                "source": assistant_turn.source if assistant_turn is not None else ctx.source,
                "locale": locale_resolution.locale,
                "response_key": response_key,
                "response_provenance": (
                    assistant_turn.response_provenance if assistant_turn is not None else None
                ),
                "fallback_reason": (
                    assistant_turn.fallback_reason if assistant_turn is not None else ctx.fallback_reason
                ),
            }
        )

        if assistant_turn is not None and assistant_turn.source == "fallback":
            self.observability.info(
                "orchestrator_fallback",
                session_id=ctx.session_id,
                fallback_reason=assistant_turn.fallback_reason,
                locale=locale_resolution.locale,
                locale_source=locale_resolution.source,
                locale_fallback_reason=locale_resolution.locale_fallback_reason,
                requested_locale=locale_resolution.requested_locale,
                latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
        primary_skill = ctx.skill_attempted[0] if len(ctx.skill_attempted) == 1 else None
        self.observability.info(
            "orchestrator_run",
            session_id=ctx.session_id,
            intent=ctx.intent.intent if ctx.intent is not None else None,
            skill=primary_skill,
            latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )
        try:
            self.session_store.save(context)
        except Exception as exc:
            self.observability.error(
                "orchestrator_session_save_failed",
                session_id=ctx.session_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        return context

    def _prepare_audio_message(
        self,
        session_id: str,
        strip_request: dict[str, Any],
    ) -> PreparedAudioUpload:
        """Sanitize and transcribe audio uploads before normal routing continues."""

        tool = find_tool(self.skill_registry, STRIP_METADATA_TOOL_ID)
        if tool is None:
            raise SkillRegistrationError(
                "Audio uploads require the strip_metadata tool to be registered."
            )
        result = dict(tool.invoke(dict(strip_request)))
        raw_transcription_text = result.get("transcription_text")
        transcription_text = None
        if raw_transcription_text is not None:
            normalized_text = str(raw_transcription_text).strip()
            if normalized_text:
                transcription_text = normalized_text
        if transcription_text is not None:
            self.observability.info(
                "orchestrator_audio_transcription",
                session_id=session_id,
                media_kind="audio",
            )
        else:
            self.observability.info(
                "orchestrator_audio_transcription_skipped",
                session_id=session_id,
                media_kind="audio",
                reason="transcription_unavailable",
            )
        return self.PreparedAudioUpload(
            strip_result=result,
            transcription_text=transcription_text,
        )

    def _record_strip_metadata_result(
        self,
        *,
        session_id: str,
        locale: str,
        strip_result: dict[str, Any],
    ) -> None:
        """Emit the strip-metadata observability event for precomputed media uploads."""

        self.observability.info(
            "orchestrator_strip_metadata",
            session_id=session_id,
            logical_path=str(strip_result["logical_path"]),
            media_kind=str(strip_result["media_kind"]),
            locale=locale,
        )

    def _response_assembly_step(self) -> ResponseAssemblyStep | None:
        """Return the configured response-assembly step when present."""

        for step in self._pipeline.steps:
            if isinstance(step, ResponseAssemblyStep):
                return step
        return None

    def _complete_precomputed_strip_metadata_turn(
        self,
        context: SessionContext,
        *,
        session_id: str,
        message: str,
        locale_resolution: Any,
        request_metadata: dict[str, Any],
        strip_result: dict[str, Any],
        started_at: float,
    ) -> SessionContext:
        """Finalize a turn that already computed a strip-metadata success result."""

        response_assembly_step = self._response_assembly_step()
        if response_assembly_step is None:
            raise InternalError("Response assembly step is not registered.")

        context.turns.append({"role": "user", "message": message})
        ctx = TurnContext(
            session=context,
            session_id=session_id,
            message=message,
            locale=locale_resolution.locale,
            locale_resolution=locale_resolution,
            request_metadata=request_metadata,
            strip_request=None,
        )
        ctx.skill_results = [
            SkillExecutionResult(
                skill_id="strip_metadata",
                outcome="success",
                payload=dict(strip_result),
            )
        ]
        ctx.skill_attempted = ["strip_metadata"]
        response_assembly_step.run(ctx)
        return self._finalize_context(
            context,
            ctx,
            locale_resolution=locale_resolution,
            started_at=started_at,
        )

    @staticmethod
    def _is_audio_strip_request(strip_request: dict[str, Any] | None) -> bool:
        if strip_request is None:
            return False
        content_type = str(strip_request.get("content_type", "")).split(";", maxsplit=1)[0]
        return content_type.strip().lower().startswith("audio/")

    @staticmethod
    def _stream_text_chunks(text: str, *, chunk_size: int = 120) -> Iterator[str]:
        """Yield stable text chunks for SSE transport without altering content."""

        if not text:
            return
        for index in range(0, len(text), chunk_size):
            yield text[index : index + chunk_size]

    def build_query_output(
        self,
        context: SessionContext,
        *,
        request_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the canonical query output payload from a completed session turn."""

        context_attributes = getattr(context, "attributes", {})
        if not isinstance(context_attributes, dict):
            context_attributes = {}
        request_metadata = dict(request_metadata or {})
        response = str(context_attributes.get("last_response", ""))
        resolved_dog_id = context_attributes.get("dog_id", request_metadata.get("dog_id"))
        response_metadata: dict[str, Any] = {
            "turn_count": len(context.turns),
            "dog_id": resolved_dog_id,
        }
        dog_profile_result = context_attributes.get(DOG_PROFILE_RESULT_METADATA_KEY)
        if isinstance(dog_profile_result, dict):
            response_metadata[DOG_PROFILE_RESULT_METADATA_KEY] = dict(dog_profile_result)
        strip_metadata_requested = STRIP_METADATA_REQUEST_METADATA_KEY in request_metadata
        if strip_metadata_requested:
            strip_metadata_result = context_attributes.get(STRIP_METADATA_RESULT_METADATA_KEY)
            if isinstance(strip_metadata_result, dict):
                response_metadata[STRIP_METADATA_RESULT_METADATA_KEY] = dict(strip_metadata_result)
        turn_debug = context_attributes.get(TURN_DEBUG_METADATA_KEY)
        if isinstance(turn_debug, dict):
            response_metadata[TURN_DEBUG_METADATA_KEY] = dict(turn_debug)
        return {
            "session_id": context.session_id,
            "response": response,
            "metadata": response_metadata,
            "error": None,
        }

    def stream_run(self, session_id: str, message: str) -> Iterator[dict[str, Any]]:
        """Yield streaming query events for the completed turn."""

        request_context = get_current_context()
        request_metadata = dict(request_context.metadata) if request_context is not None else {}
        try:
            started_at = time.perf_counter()
            context = self.session_store.load(session_id)

            try:
                strip_request = extract_strip_metadata_request(request_metadata)
            except ValueError as exc:
                raise DomainError("Invalid strip_metadata_request metadata.") from exc

            audio_upload: GraphOrchestrator.PreparedAudioUpload | None = None
            original_message = message
            if self._is_audio_strip_request(strip_request):
                audio_upload = self._prepare_audio_message(session_id, strip_request)
                context.attributes[STRIP_METADATA_RESULT_METADATA_KEY] = dict(audio_upload.strip_result)
                if audio_upload.transcription_text is not None:
                    message = audio_upload.transcription_text
                strip_request = None

            locale_resolution = resolve_locale(
                message=message,
                request_metadata=request_metadata,
                context_attributes=context.attributes,
            )
            if locale_resolution.source == "metadata":
                context.attributes[PREFERRED_LOCALE_ATTRIBUTE_KEY] = locale_resolution.locale
            elif (
                locale_resolution.source == "context"
                and PREFERRED_LOCALE_ATTRIBUTE not in context.attributes
            ):
                context.attributes[PREFERRED_LOCALE_ATTRIBUTE_KEY] = locale_resolution.locale

            if audio_upload is not None:
                self._record_strip_metadata_result(
                    session_id=session_id,
                    locale=locale_resolution.locale,
                    strip_result=audio_upload.strip_result,
                )
                if audio_upload.transcription_text is None:
                    context = self._complete_precomputed_strip_metadata_turn(
                        context,
                        session_id=session_id,
                        message=original_message,
                        locale_resolution=locale_resolution,
                        request_metadata=request_metadata,
                        strip_result=audio_upload.strip_result,
                        started_at=started_at,
                    )
                    output = self.build_query_output(context, request_metadata=request_metadata)
                    for chunk in self._stream_text_chunks(output["response"]):
                        yield {
                            "event": "query.delta",
                            "session_id": output["session_id"],
                            "delta": chunk,
                        }
                    yield {
                        "event": "query.completed",
                        "session_id": output["session_id"],
                        "output": output,
                    }
                    return

            is_new_session = len(context.turns) == 0
            if is_new_session:
                channel = str(request_metadata.get("channel", "direct")).strip() or "direct"
                record_session_started(channel=channel)
            if is_new_session and not message.strip() and strip_request is None:
                known_profiles = list_known_dog_profiles(
                    request_metadata,
                    self.dog_profile_db_adapter,
                )
                returning_dog_name = resolve_active_dog_name(
                    context,
                    request_metadata,
                    self.dog_profile_db_adapter,
                )
                if returning_dog_name is None and len(known_profiles) == 1:
                    returning_dog_name = str(known_profiles[0].name).strip() or None
                if returning_dog_name is not None:
                    welcome_message = build_fallback_message(
                        locale=locale_resolution.locale,
                        reason="fallback.greeting",
                        dog_name=returning_dog_name,
                    )
                elif len(known_profiles) > 1:
                    welcome_message = build_active_dog_selection_prompt(
                        locale=locale_resolution.locale,
                        dog_names=tuple(
                            str(profile.name).strip()
                            for profile in known_profiles
                            if str(profile.name).strip()
                        ),
                    )
                else:
                    welcome_message = build_session_welcome(locale=locale_resolution.locale)
                context.attributes["last_response"] = welcome_message.text
                context.attributes[TURN_DEBUG_METADATA_KEY] = {
                    "intent": None,
                    "matched_skills": [],
                    "intent_confidence": None,
                    "intent_reasoning": None,
                    "source": "welcome",
                    "response_key": welcome_message.key,
                    "response_provenance": "deterministic",
                    "locale": locale_resolution.locale,
                    "locale_source": locale_resolution.source,
                    "requested_locale": locale_resolution.requested_locale,
                    "locale_fallback_reason": locale_resolution.locale_fallback_reason,
                    "fallback_reason": None,
                    "skill_attempted": [],
                    "skill_error": None,
                    "updated_fields": [],
                    "raw_note_saved": False,
                    "safety_boundary_hit": False,
                }
                context.turns.append(
                    {
                        "role": "assistant",
                        "message": welcome_message.text,
                        "source": "welcome",
                        "locale": locale_resolution.locale,
                        "response_key": welcome_message.key,
                        "response_provenance": "deterministic",
                        "fallback_reason": None,
                    }
                )
                self.observability.info(
                    "orchestrator_welcome",
                    session_id=session_id,
                    locale=locale_resolution.locale,
                    locale_source=locale_resolution.source,
                    locale_fallback_reason=locale_resolution.locale_fallback_reason,
                    requested_locale=locale_resolution.requested_locale,
                    response_key=welcome_message.key,
                    latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
                )
                self.observability.info(
                    "orchestrator_run",
                    session_id=session_id,
                    intent=None,
                    skill=None,
                    latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
                )
                self.session_store.save(context)
                output = self.build_query_output(context, request_metadata=request_metadata)
                for chunk in self._stream_text_chunks(output["response"]):
                    yield {
                        "event": "query.delta",
                        "session_id": output["session_id"],
                        "delta": chunk,
                    }
                yield {
                    "event": "query.completed",
                    "session_id": output["session_id"],
                    "output": output,
                }
                return

            context.turns.append({"role": "user", "message": message})
            ctx = TurnContext(
                session=context,
                session_id=session_id,
                message=message,
                locale=locale_resolution.locale,
                locale_resolution=locale_resolution,
                request_metadata=request_metadata,
                strip_request=strip_request,
            )

            response_assembly_step = self._response_assembly_step()
            for step in self._pipeline.steps:
                if step is response_assembly_step:
                    break
                step.run(ctx)
                if ctx.is_terminal:
                    break

            emitted_delta = False
            if (
                not ctx.is_terminal
                and response_assembly_step is not None
                and response_assembly_step.can_stream_conversational_fallback(ctx)
            ):
                stream = response_assembly_step.stream_conversational_fallback(ctx)
                assistant_turn = None
                while True:
                    try:
                        chunk = next(stream)
                    except StopIteration as stop:
                        assistant_turn = stop.value
                        break
                    if not chunk:
                        continue
                    emitted_delta = True
                    yield {
                        "event": "query.delta",
                        "session_id": session_id,
                        "delta": chunk,
                    }
                if assistant_turn is None:
                    raise InternalError("Streaming fallback did not assemble a final assistant turn.")
                ResponseAssemblyStep._apply_assistant_turn(ctx, assistant_turn)
            elif not ctx.is_terminal and response_assembly_step is not None:
                response_assembly_step.run(ctx)

            context = self._finalize_context(
                context,
                ctx,
                locale_resolution=locale_resolution,
                started_at=started_at,
            )
            output = self.build_query_output(context, request_metadata=request_metadata)
            if not emitted_delta:
                for chunk in self._stream_text_chunks(output["response"]):
                    yield {
                        "event": "query.delta",
                        "session_id": output["session_id"],
                        "delta": chunk,
                    }
            yield {
                "event": "query.completed",
                "session_id": output["session_id"],
                "output": output,
            }
        except TailmateError as exc:
            yield {
                "event": "query.completed",
                "session_id": session_id,
                "output": {
                    "session_id": session_id,
                    "response": "",
                    "metadata": {"dog_id": request_metadata.get("dog_id")},
                    "error": exc.to_error_detail(),
                },
            }
        except Exception:
            error = InternalError()
            yield {
                "event": "query.completed",
                "session_id": session_id,
                "output": {
                    "session_id": session_id,
                    "response": "",
                    "metadata": {"dog_id": request_metadata.get("dog_id")},
                    "error": error.to_error_detail(),
                },
            }
