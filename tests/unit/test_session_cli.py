from __future__ import annotations

import argparse
import importlib

from tailmate.agent_runtime.models.session_context import SessionContext


class FakeConversationStore:
    def __init__(self, context: SessionContext | None = None, *, deleted: bool = False) -> None:
        self.context = context
        self.deleted = deleted
        self.deleted_session_ids: list[str] = []
        self.loaded_session_ids: list[str] = []

    def load_optional(self, session_id: str) -> SessionContext | None:
        self.loaded_session_ids.append(session_id)
        return self.context

    def delete(self, session_id: str) -> bool:
        self.deleted_session_ids.append(session_id)
        return self.deleted


def test_build_parser_registers_session_commands(monkeypatch) -> None:
    module = importlib.import_module("tailmate.entrypoints.cli")

    inspect_args = module.build_parser().parse_args(["session", "inspect", "session-1"])
    delete_args = module.build_parser().parse_args(["session", "delete", "session-1", "--yes"])

    assert inspect_args.command == "session"
    assert inspect_args.session_command == "inspect"
    assert inspect_args.func.__name__ == "run_session_inspect"
    assert delete_args.session_command == "delete"
    assert delete_args.func.__name__ == "run_session_delete"


def test_run_session_inspect_prints_json(monkeypatch, capsys) -> None:
    module = importlib.import_module("tailmate.entrypoints.session_inspect")
    store = FakeConversationStore(
        SessionContext(
            session_id="session-1",
            turns=[{"role": "user", "message": "hi"}],
            attributes={"dog_id": "dog-1"},
        )
    )
    monkeypatch.setattr(module, "build_local_conversation_store", lambda: store)

    exit_code = module.run_session_inspect(argparse.Namespace(session_id="session-1"))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert store.loaded_session_ids == ["session-1"]
    assert '"session_id": "session-1"' in captured.out
    assert '"dog_id": "dog-1"' in captured.out


def test_run_session_inspect_reports_missing_session(monkeypatch, capsys) -> None:
    module = importlib.import_module("tailmate.entrypoints.session_inspect")
    monkeypatch.setattr(module, "build_local_conversation_store", lambda: FakeConversationStore())

    exit_code = module.run_session_inspect(argparse.Namespace(session_id="missing"))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Session 'missing' does not exist." in captured.err


def test_run_session_delete_requires_yes(monkeypatch, capsys) -> None:
    module = importlib.import_module("tailmate.entrypoints.session_delete")

    exit_code = module.run_session_delete(argparse.Namespace(session_id="session-1", yes=False))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "without --yes" in captured.err


def test_run_session_delete_reports_success(monkeypatch, capsys) -> None:
    module = importlib.import_module("tailmate.entrypoints.session_delete")
    store = FakeConversationStore(deleted=True)
    monkeypatch.setattr(module, "build_local_conversation_store", lambda: store)

    exit_code = module.run_session_delete(argparse.Namespace(session_id="session-1", yes=True))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert store.deleted_session_ids == ["session-1"]
    assert "Deleted session 'session-1'." in captured.out


def test_run_session_delete_reports_missing_session(monkeypatch, capsys) -> None:
    module = importlib.import_module("tailmate.entrypoints.session_delete")
    store = FakeConversationStore(deleted=False)
    monkeypatch.setattr(module, "build_local_conversation_store", lambda: store)

    exit_code = module.run_session_delete(argparse.Namespace(session_id="session-1", yes=True))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert store.deleted_session_ids == ["session-1"]
    assert "Session 'session-1' does not exist." in captured.err
