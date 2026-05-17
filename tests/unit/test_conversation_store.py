from __future__ import annotations

from tailmate.adapters.database.conversation_store import DatabaseConversationStore
from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.adapters.database.models import metadata
from tailmate.agent_runtime.models.session_context import SessionContext


def test_database_conversation_store_loads_and_saves(tmp_path) -> None:
    database_path = tmp_path / "tailmate.sqlite"
    factory = DatabaseEngineFactory(f"sqlite:///{database_path}")
    engine = factory.create()
    metadata.create_all(engine)
    engine.dispose()

    store = DatabaseConversationStore(engine_factory=factory)
    context = SessionContext(
        session_id="session-1",
        turns=[{"role": "user", "message": "hello"}],
        attributes={"dog_id": "dog-1"},
    )

    store.save(context)
    loaded = store.load("session-1")

    assert loaded.session_id == "session-1"
    assert loaded.turns == [{"role": "user", "message": "hello"}]
    assert loaded.attributes == {"dog_id": "dog-1"}


def test_database_conversation_store_save_turn_appends_history(tmp_path) -> None:
    database_path = tmp_path / "tailmate.sqlite"
    factory = DatabaseEngineFactory(f"sqlite:///{database_path}")
    engine = factory.create()
    metadata.create_all(engine)
    engine.dispose()

    store = DatabaseConversationStore(engine_factory=factory)
    store.save_turn("session-2", {"role": "user", "message": "first"})
    store.save_turn("session-2", {"role": "assistant", "message": "second"})

    assert store.load_history("session-2") == [
        {"role": "user", "message": "first"},
        {"role": "assistant", "message": "second"},
    ]
