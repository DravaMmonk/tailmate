"""Shared mutable state for a single orchestration turn."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from tailmate.agent_runtime.models.session_context import SessionContext
from tailmate.contracts.types import ResponseProvenance


@dataclass(frozen=True)
class DogProfileTurnResult:
    """Structured outcome for one dog-profile orchestration attempt."""

    outcome: str
    created_name: str | None = None
    updated_fields: tuple[str, ...] = ()
    raw_note_present: bool = False
    attempted_tools: tuple[str, ...] = ()
    skill_error: dict[str, str] | None = None


IntentKind = Literal["known", "open"]


@dataclass(frozen=True)
class IntentClassification:
    """Structured routing decision produced before any skill execution."""

    intent: IntentKind
    matched_skills: tuple[str, ...]
    confidence: float | None = None
    reasoning: str | None = None


@dataclass(frozen=True)
class SkillExecutionResult:
    """Structured outcome for one executed skill."""

    skill_id: str
    outcome: str
    payload: dict[str, Any]
    error: dict[str, str] | None = None
    duration_ms: int | None = None


@dataclass(frozen=True)
class AssistantTurn:
    """Fully assembled assistant response for one turn."""

    message: str
    source: str
    response_key: str
    skill_results: tuple[SkillExecutionResult, ...]
    response_provenance: ResponseProvenance
    fallback_reason: str | None = None
    skill_id: str | None = None


@dataclass
class TurnContext:
    """Mutable state shared across routing steps for one orchestration turn.

    Steps read from and write to this object.  A step signals that it has
    produced a terminal response by setting ``is_terminal = True``; the
    pipeline stops iterating after any terminal step.
    """

    # ── Inputs (set once before the pipeline starts) ────────────────────
    session: SessionContext
    session_id: str
    message: str
    locale: str
    locale_resolution: Any  # LocaleResolution
    request_metadata: dict[str, Any]
    strip_request: Any  # StripMetadataRequest | None

    # ── Accumulated intermediate state (mutated by steps) ───────────────
    intent: IntentClassification | None = None
    skill_results: list[SkillExecutionResult] = field(default_factory=list)
    execution_phase_started_at: float | None = None
    dog_profile_result: DogProfileTurnResult | None = None
    current_dog_profile: Any | None = None   # DogProfile | None
    dog_selection: Any | None = None         # DogSelectionResolution | None
    dog_context: str | None = None           # formatted profile snapshot for KB
    knowledge_message: str | None = None     # augmented message for KB (None → use message)
    knowledge_result: Any | None = None      # KnowledgeQueryOutput | None

    # ── Terminal output (set by the first step that handles this turn) ───
    assistant_turn: AssistantTurn | None = None
    response: Any | None = None              # LocalizedTurnMessage | None
    skill_id: str | None = None
    source: str | None = None
    fallback_reason: str | None = None
    is_terminal: bool = False

    # ── Observability metadata (accumulated by steps) ───────────────────
    skill_attempted: list[str] = field(default_factory=list)
    skill_error: dict[str, str] | None = None
    updated_fields: list[str] = field(default_factory=list)
    raw_note_saved: bool = False
    safety_boundary_hit: bool = False

    @property
    def effective_knowledge_message(self) -> str:
        """Message to pass to the knowledge base.

        Returns the augmented ``knowledge_message`` when set by
        ``DogContextStep``, otherwise the raw ``message``.
        """
        return self.knowledge_message if self.knowledge_message is not None else self.message
