"""Hybrid intent classifier that escalates uncertain routing to Gemini."""

from __future__ import annotations

from dataclasses import dataclass

from tailmate.agent_runtime.pipeline.turn_context import IntentClassification, TurnContext
from tailmate.agent_runtime.ports.intent_classifier import IntentClassifier
from tailmate.agent_runtime.ports.skill_registry import SkillRegistry


@dataclass
class HybridIntentClassifier:
    """Keep deterministic routing for clear cases and use LLM fallback otherwise."""

    skill_registry: SkillRegistry
    rule_classifier: IntentClassifier
    llm_classifier: IntentClassifier | None = None
    confidence_threshold: float = 0.7

    def classify(self, ctx: TurnContext) -> IntentClassification:
        rule_result = self._normalize(self.rule_classifier.classify(ctx))
        if self._should_accept_rule_result(rule_result):
            return rule_result
        if self.llm_classifier is None:
            return rule_result
        try:
            llm_result = self._normalize(self.llm_classifier.classify(ctx))
        except Exception:
            return rule_result
        if (llm_result.confidence or 0.0) < self.confidence_threshold:
            return IntentClassification(
                intent=rule_result.intent,
                matched_skills=rule_result.matched_skills,
                confidence=rule_result.confidence,
                reasoning=rule_result.reasoning,
            )
        return llm_result

    def _normalize(self, classification: IntentClassification) -> IntentClassification:
        matched_skills = tuple(
            skill_id
            for skill_id in classification.matched_skills
            if skill_id in self._known_skill_ids()
        )
        if classification.intent == "open":
            if "knowledge_base" in self._known_skill_ids() and "knowledge_base" not in matched_skills:
                matched_skills = matched_skills + ("knowledge_base",)
        return IntentClassification(
            intent=classification.intent,
            matched_skills=matched_skills,
            confidence=classification.confidence,
            reasoning=classification.reasoning,
        )

    @staticmethod
    def _should_accept_rule_result(classification: IntentClassification) -> bool:
        return (
            classification.intent == "known"
            and "knowledge_base" not in classification.matched_skills
        )

    def _known_skill_ids(self) -> frozenset[str]:
        return frozenset(skill.skill_id for skill in self.skill_registry.skills())
