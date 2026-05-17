"""Builds the root runtime from specs and adapters."""

from __future__ import annotations

from tailmate.agents.root.assembly import assemble_root_orchestrator
from tailmate.agent_runtime.ports.conversational_responder import ConversationalResponder
from tailmate.agent_runtime.ports.dog_profile_db_adapter import DogProfileDBAdapter
from tailmate.agent_runtime.ports.intent_classifier import IntentClassifier
from tailmate.agent_runtime.ports.knowledge_retriever import KnowledgeRetriever
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.agent_runtime.ports.session_store import SessionStore
from tailmate.agent_runtime.ports.skill_registry import SkillRegistry


def build_root_orchestrator(
    *,
    session_store: SessionStore,
    observability: Observability,
    skill_registry: SkillRegistry,
    intent_classifier: IntentClassifier,
    dog_profile_db_adapter: DogProfileDBAdapter | None = None,
    knowledge_retriever: KnowledgeRetriever | None = None,
    conversational_responder: ConversationalResponder | None = None,
):
    """Builds the canonical root orchestrator graph."""

    return assemble_root_orchestrator(
        session_store=session_store,
        observability=observability,
        skill_registry=skill_registry,
        dog_profile_db_adapter=dog_profile_db_adapter,
        knowledge_retriever=knowledge_retriever,
        conversational_responder=conversational_responder,
        intent_classifier=intent_classifier,
    )
