from __future__ import annotations

import logging
from pathlib import Path
import tempfile

from google.auth.credentials import AnonymousCredentials
from google.api_core.exceptions import NotFound
import pytest

from tailmate.adapters.gcs.gcs_adapter import GcsBlobStore
from tailmate.adapters.localfs.blob_store import LocalBlobStore
from tailmate.contracts.errors import AdapterError


class FakeBlob:
    def __init__(
        self,
        *,
        failures_before_success: int = 0,
        delete_error: Exception | None = None,
    ) -> None:
        self.calls: list[tuple[bytes, str]] = []
        self.deleted = False
        self.failures_before_success = failures_before_success
        self.upload_attempts = 0
        self.delete_error = delete_error

    def upload_from_string(self, payload: bytes, content_type: str) -> None:
        self.upload_attempts += 1
        if self.upload_attempts <= self.failures_before_success:
            raise RuntimeError("transient gcs failure")
        self.calls.append((payload, content_type))

    def delete(self) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted = True


class FakeBucket:
    def __init__(
        self,
        *,
        failures_before_success: int = 0,
        delete_error: Exception | None = None,
    ) -> None:
        self.blobs: dict[str, FakeBlob] = {}
        self.failures_before_success = failures_before_success
        self.delete_error = delete_error

    def blob(self, object_name: str) -> FakeBlob:
        blob = FakeBlob(
            failures_before_success=self.failures_before_success,
            delete_error=self.delete_error,
        )
        self.blobs[object_name] = blob
        return blob


class FakeClient:
    def __init__(
        self,
        *,
        failures_before_success: int = 0,
        delete_error: Exception | None = None,
    ) -> None:
        self.buckets: dict[str, FakeBucket] = {}
        self.failures_before_success = failures_before_success
        self.delete_error = delete_error

    def bucket(self, bucket_name: str) -> FakeBucket:
        bucket = self.buckets.setdefault(
            bucket_name,
            FakeBucket(
                failures_before_success=self.failures_before_success,
                delete_error=self.delete_error,
            ),
        )
        return bucket


def test_gcs_blob_store_uploads_with_sdk_client() -> None:
    fake_client = FakeClient()
    store = GcsBlobStore(bucket_name="tailmate-media", project_id="test-project")
    store._client = fake_client

    logical_path = store.put("dogs/dog-1/videos/sample.txt", "text/plain", b"tailmate")

    assert logical_path == "dogs/dog-1/videos/sample.txt"
    assert fake_client.buckets["tailmate-media"].blobs["dogs/dog-1/videos/sample.txt"].calls == [
        (b"tailmate", "text/plain")
    ]
    assert (
        store.resolve_resource("dogs/dog-1/videos/sample.txt")
        == "gs://tailmate-media/dogs/dog-1/videos/sample.txt"
    )
    store.delete("dogs/dog-1/videos/sample.txt")
    assert fake_client.buckets["tailmate-media"].blobs["dogs/dog-1/videos/sample.txt"].deleted is True


def test_gcs_blob_store_retries_transient_upload_failures_before_succeeding(
    monkeypatch,
) -> None:
    monkeypatch.setattr("tailmate.adapters.gcs.gcs_adapter.tenacity.sleep", lambda _seconds: None)
    fake_client = FakeClient(failures_before_success=2)
    store = GcsBlobStore(bucket_name="tailmate-media", project_id="test-project")
    store._client = fake_client

    logical_path = store.put("dogs/dog-1/videos/sample.txt", "text/plain", b"tailmate")

    assert logical_path == "dogs/dog-1/videos/sample.txt"
    blob = fake_client.buckets["tailmate-media"].blobs["dogs/dog-1/videos/sample.txt"]
    assert blob.upload_attempts == 3
    assert blob.calls == [(b"tailmate", "text/plain")]


def test_gcs_blob_store_logs_and_raises_after_retry_exhaustion(
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setattr("tailmate.adapters.gcs.gcs_adapter.tenacity.sleep", lambda _seconds: None)
    fake_client = FakeClient(failures_before_success=3)
    store = GcsBlobStore(bucket_name="tailmate-media", project_id="test-project")
    store._client = fake_client

    with caplog.at_level(logging.ERROR):
        with pytest.raises(AdapterError, match="Failed to upload GCS blob"):
            store.put("dogs/dog-1/videos/sample.txt", "text/plain", b"tailmate")

    blob = fake_client.buckets["tailmate-media"].blobs["dogs/dog-1/videos/sample.txt"]
    assert blob.upload_attempts == 3
    record = next(
        entry for entry in caplog.records if entry.getMessage() == "gcs.upload_failed_after_retries"
    )
    assert record.bucket_name == "tailmate-media"
    assert record.object_name == "dogs/dog-1/videos/sample.txt"
    assert record.attempts == 3
    assert record.error_type == "RuntimeError"


def test_gcs_blob_store_uses_anonymous_credentials_for_emulator() -> None:
    store = GcsBlobStore(
        bucket_name="tailmate-media",
        project_id="test-project",
        api_endpoint="http://127.0.0.1:4443",
    )

    client = store.client

    assert isinstance(client._credentials, AnonymousCredentials)


def test_gcs_blob_store_delete_is_idempotent_for_missing_objects() -> None:
    fake_client = FakeClient(delete_error=NotFound("missing"))
    store = GcsBlobStore(bucket_name="tailmate-media", project_id="test-project")
    store._client = fake_client

    store.delete("dogs/dog-1/videos/sample.txt")

    assert fake_client.buckets["tailmate-media"].blobs["dogs/dog-1/videos/sample.txt"].deleted is False


def test_local_blob_store_resolves_file_uri() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        store = LocalBlobStore(root_dir=Path(temp_dir))

        logical_path = store.put("dogs/dog-1/videos/sample.txt", "text/plain", b"tailmate")
        resolved = store.resolve_resource(logical_path)

        assert logical_path == "dogs/dog-1/videos/sample.txt"
        assert resolved.startswith("file://")
        assert Path(resolved.removeprefix("file://")).read_bytes() == b"tailmate"
        store.delete(logical_path)
        assert not Path(resolved.removeprefix("file://")).exists()
