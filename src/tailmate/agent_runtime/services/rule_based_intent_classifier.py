"""Rule-based intent classifier extracted from runtime skill routing."""

from __future__ import annotations

from dataclasses import dataclass

from tailmate.agent_runtime.pipeline.turn_context import IntentClassification, TurnContext
from tailmate.agent_runtime.ports.skill_registry import SkillRegistry


@dataclass
class RuleBasedIntentClassifier:
    """Run the existing runtime-skill classification loop verbatim."""

    skill_registry: SkillRegistry

    def classify(self, ctx: TurnContext) -> IntentClassification:
        matches: list[tuple[object, object]] = []
        for skill in self.skill_registry.skills():
            match = skill.classify(ctx)
            if match is not None:
                matches.append((skill, match))

        if not matches:
            return IntentClassification(intent="open", matched_skills=())

        matches.sort(key=lambda item: item[1].priority, reverse=True)
        winning_intent = matches[0][1].intent
        matched_skills = tuple(
            skill.skill_id
            for skill, match in matches
            if match.intent == winning_intent
        )
        confidence = 1.0 if winning_intent == "known" else 0.0
        reasoning = (
            "Matched explicit runtime skill rules."
            if winning_intent == "known"
            else "No explicit runtime skill rules matched."
        )
        return IntentClassification(
            intent=winning_intent,
            matched_skills=matched_skills,
            confidence=confidence,
            reasoning=reasoning,
        )
