from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine

from tailmate.adapters.database.conversation_store import DatabaseConversationStore
from tailmate.adapters.database.models import conversation_sessions, metadata


@dataclass
class SingleEngineFactory:
    engine: object

    def create(self):
        return self.engine


def test_database_conversation_store_load_optional_and_delete(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'conversation-store.db'}")
    metadata.create_all(engine)
    store = DatabaseConversationStore(engine_factory=SingleEngineFactory(engine))

    assert store.load_optional("missing") is None
    assert store.delete("missing") is False

    with engine.begin() as connection:
        connection.execute(
            conversation_sessions.insert().values(
                session_id="session-1",
                turns=[{"role": "user", "message": "hello"}],
                attributes={"dog_id": "dog-1"},
            )
        )

    context = store.load_optional("session-1")

    assert context is not None
    assert context.session_id == "session-1"
    assert context.turns == [{"role": "user", "message": "hello"}]
    assert context.attributes == {"dog_id": "dog-1"}
    assert store.delete("session-1") is True
    assert store.load_optional("session-1") is None

    engine.dispose()
