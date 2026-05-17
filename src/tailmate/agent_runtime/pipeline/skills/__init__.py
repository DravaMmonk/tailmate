"""Runtime skill implementations used by orchestration pipeline steps."""

from __future__ import annotations

from tailmate.agent_runtime.ports.dog_profile_db_adapter import DogProfileDBAdapter
from tailmate.agent_runtime.ports.knowledge_retriever import KnowledgeRetriever
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.skills.registry import InMemorySkillRegistry

from .dog_profile_create import DogProfileCreateRuntimeSkill
from .dog_profile_enrich import DogProfileEnrichRuntimeSkill
from .dog_profile_recall import DogProfileRecallRuntimeSkill
from .dog_profile_switch import DogProfileSwitchRuntimeSkill
from .knowledge_base import KnowledgeBaseRuntimeSkill
from .strip_metadata import StripMetadataRuntimeSkill


def register_standard_runtime_skills(
    registry: InMemorySkillRegistry,
    *,
    dog_profile_db_adapter: DogProfileDBAdapter | None = None,
    knowledge_retriever: KnowledgeRetriever | None = None,
    observability: Observability | None = None,
    conversational_responder_available: bool = False,
) -> InMemorySkillRegistry:
    """Register the default runtime skills used by the turn pipeline."""

    registry.register_runtime_skill(
        StripMetadataRuntimeSkill(
            skill_registry=registry,
            observability=observability,
        )
    )
    registry.register_runtime_skill(
        DogProfileCreateRuntimeSkill(
            skill_registry=registry,
            dog_profile_db_adapter=dog_profile_db_adapter,
            observability=observability,
        )
    )
    registry.register_runtime_skill(
        DogProfileSwitchRuntimeSkill(
            dog_profile_db_adapter=dog_profile_db_adapter,
            observability=observability,
        )
    )
    registry.register_runtime_skill(
        DogProfileEnrichRuntimeSkill(
            skill_registry=registry,
            dog_profile_db_adapter=dog_profile_db_adapter,
            observability=observability,
        )
    )
    registry.register_runtime_skill(
        DogProfileRecallRuntimeSkill(
            dog_profile_db_adapter=dog_profile_db_adapter,
            observability=observability,
        )
    )
    registry.register_runtime_skill(
        KnowledgeBaseRuntimeSkill(
            skill_registry=registry,
            dog_profile_db_adapter=dog_profile_db_adapter,
            knowledge_retriever=knowledge_retriever,
            observability=observability,
            conversational_responder_available=conversational_responder_available,
        )
    )
    return registry
