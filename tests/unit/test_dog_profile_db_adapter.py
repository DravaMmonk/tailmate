from __future__ import annotations

from types import SimpleNamespace

import pytest

from tailmate.adapters.dog_profile.db_adapter import DatabaseDogProfileDBAdapter
from tailmate.contracts.errors import AuthorizationError
from tailmate.observability import LogContext, reset_log_context, set_log_context


class FakeAuditLogger:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def record(self, **event) -> None:
        self.events.append(event)


class FailingAuditLogger(FakeAuditLogger):
    def record(self, **event) -> None:
        del event
        raise RuntimeError("audit unavailable")


def build_adapter(*, audit_logger: FakeAuditLogger | None = None) -> DatabaseDogProfileDBAdapter:
    return DatabaseDogProfileDBAdapter(
        engine_factory=SimpleNamespace(create=lambda: None),
        audit_logger=audit_logger,
    )


def test_load_profile_returns_profile_for_owner(monkeypatch) -> None:
    adapter = build_adapter()
    monkeypatch.setattr(
        adapter,
        "_load_raw_profile_row",
        lambda _dog_id: {
            "id": "dog-1",
            "user_id": "user-1",
            "name": "DouDou",
        },
    )

    profile = adapter.load_profile("dog-1", requesting_user_id="user-1")

    assert profile is not None
    assert profile.dog_id == "dog-1"
    assert profile.user_id == "user-1"
    assert profile.name == "DouDou"


def test_load_profile_rejects_cross_user_access(monkeypatch) -> None:
    adapter = build_adapter()
    monkeypatch.setattr(
        adapter,
        "_load_raw_profile_row",
        lambda _dog_id: {
            "id": "dog-1",
            "user_id": "user-1",
            "name": "DouDou",
        },
    )

    with pytest.raises(AuthorizationError, match="User does not own dog profile 'dog-1'."):
        adapter.load_profile("dog-1", requesting_user_id="user-2")


def test_create_profile_records_audit_event() -> None:
    audit_logger = FakeAuditLogger()
    adapter = build_adapter(audit_logger=audit_logger)
    fake_connection = SimpleNamespace(execute=lambda *_args, **_kwargs: None)

    class FakeBegin:
        def __enter__(self):
            return fake_connection

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_engine = SimpleNamespace(begin=lambda: FakeBegin(), dispose=lambda: None)
    adapter.engine_factory = SimpleNamespace(create=lambda: fake_engine)
    request = SimpleNamespace(
        model_dump=lambda **_kwargs: {"user_id": "user-1", "name": "DouDou"},
        medical_history=None,
        allergies=None,
        current_medications=None,
        raw_notes=None,
        name="DouDou",
    )
    log_token = set_log_context(LogContext(trace_id="trace-create"))

    try:
        result = adapter.create_profile(request)
    finally:
        reset_log_context(log_token)

    assert result.dog_id
    assert audit_logger.events[0]["trace_id"] == "trace-create"
    assert audit_logger.events[0]["user_id"] == "user-1"
    assert audit_logger.events[0]["entity_type"] == "dog_profile"
    assert audit_logger.events[0]["action"] == "create"
    assert audit_logger.events[0]["before"] is None
    assert audit_logger.events[0]["after"]["name"] == "DouDou"


def test_enrich_profile_records_audit_event_when_profile_changes(monkeypatch) -> None:
    audit_logger = FakeAuditLogger()
    adapter = build_adapter(audit_logger=audit_logger)
    current_profile = SimpleNamespace(
        user_id="user-1",
        model_dump=lambda **_kwargs: {"dog_id": "dog-1", "name": "DouDou", "breed": None},
    )
    updated_profile = SimpleNamespace(
        model_dump=lambda **_kwargs: {"dog_id": "dog-1", "name": "DouDou", "breed": "Corgi"}
    )
    mutation = SimpleNamespace(
        touched=True,
        updated_profile=updated_profile,
        updated_fields={"breed": "Corgi"},
        stored_raw_note=None,
    )
    fake_connection = SimpleNamespace(execute=lambda *_args, **_kwargs: None)

    class FakeBegin:
        def __enter__(self):
            return fake_connection

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_engine = SimpleNamespace(begin=lambda: FakeBegin(), dispose=lambda: None)
    adapter.engine_factory = SimpleNamespace(create=lambda: fake_engine)
    monkeypatch.setattr(adapter, "load_profile", lambda *_args, **_kwargs: current_profile)
    monkeypatch.setattr("tailmate.adapters.dog_profile.db_adapter.apply_extraction_result", lambda *_args: mutation)
    request = SimpleNamespace(dog_id="dog-1", requesting_user_id="user-1", user_message="hello")
    extraction_result = SimpleNamespace(strategy_used="rule", structured_fields={}, confidence=0.9)
    log_token = set_log_context(LogContext(trace_id="trace-update"))

    try:
        result = adapter.enrich_profile(request, extraction_result)
    finally:
        reset_log_context(log_token)

    assert result.updated_fields == {"breed": "Corgi"}
    assert audit_logger.events[0]["trace_id"] == "trace-update"
    assert audit_logger.events[0]["action"] == "update"
    assert audit_logger.events[0]["before"]["breed"] is None
    assert audit_logger.events[0]["after"]["breed"] == "Corgi"


def test_create_profile_succeeds_when_audit_logging_fails(caplog) -> None:
    adapter = build_adapter(audit_logger=FailingAuditLogger())
    fake_connection = SimpleNamespace(execute=lambda *_args, **_kwargs: None)

    class FakeBegin:
        def __enter__(self):
            return fake_connection

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_engine = SimpleNamespace(begin=lambda: FakeBegin(), dispose=lambda: None)
    adapter.engine_factory = SimpleNamespace(create=lambda: fake_engine)
    request = SimpleNamespace(
        model_dump=lambda **_kwargs: {"user_id": "user-1", "name": "DouDou"},
        medical_history=None,
        allergies=None,
        current_medications=None,
        raw_notes=None,
        name="DouDou",
    )
    log_token = set_log_context(LogContext(trace_id="trace-create"))

    try:
        with caplog.at_level("WARNING"):
            result = adapter.create_profile(request)
    finally:
        reset_log_context(log_token)

    assert result.dog_id
    assert "dog_profile_db_adapter.audit_record_failed" in caplog.text
