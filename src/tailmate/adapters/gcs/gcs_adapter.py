"""Google Cloud Storage implementation of the blob storage port."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from collections.abc import Callable
from typing import Any

import tenacity

from google.auth.credentials import AnonymousCredentials
from google.api_core.exceptions import NotFound
from google.cloud import storage

from tailmate.adapters.localfs.blob_store import validate_logical_path
from tailmate.contracts.errors import AdapterError
from tailmate.tracing import start_span


logger = logging.getLogger(__name__)
RETRY_ATTEMPTS = 3
RETRY_INITIAL_WAIT_SECONDS = 1
RETRY_MAX_WAIT_SECONDS = 4


def _retry_external_call(
    *,
    operation: Callable[[], Any],
    failure_message: str,
    log_message: str,
    log_context: dict[str, Any],
) -> Any:
    retrying = tenacity.Retrying(
        sleep=tenacity.sleep,
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS),
        wait=tenacity.wait_exponential(
            multiplier=RETRY_INITIAL_WAIT_SECONDS,
            min=RETRY_INITIAL_WAIT_SECONDS,
            max=RETRY_MAX_WAIT_SECONDS,
        ),
        retry=tenacity.retry_if_exception_type(Exception),
        reraise=False,
    )
    try:
        return retrying(operation)
    except tenacity.RetryError as exc:
        last_attempt = exc.last_attempt
        last_exception = last_attempt.exception() if last_attempt is not None else None
        logger.error(
            log_message,
            extra={
                **log_context,
                "attempts": last_attempt.attempt_number if last_attempt is not None else RETRY_ATTEMPTS,
                "error_type": type(last_exception).__name__ if last_exception is not None else None,
                "error_message": str(last_exception) if last_exception is not None else None,
            },
        )
        if last_exception is not None:
            raise AdapterError(failure_message) from last_exception
        raise AdapterError(failure_message) from exc


@dataclass
class GcsBlobStore:
    """Stores media assets in a configured GCS bucket."""

    bucket_name: str
    project_id: str | None = None
    api_endpoint: str | None = None
    _client: storage.Client | None = field(default=None, init=False, repr=False)

    @property
    def client(self) -> storage.Client:
        if self._client is None:
            if self.api_endpoint:
                self._client = storage.Client(
                    project=self.project_id,
                    credentials=AnonymousCredentials(),
                    client_options={"api_endpoint": self.api_endpoint},
                    use_auth_w_custom_endpoint=False,
                )
            else:
                self._client = storage.Client(project=self.project_id)
        return self._client

    def put(self, logical_path: str, content_type: str, payload: bytes) -> str:
        normalized = validate_logical_path(logical_path)
        blob = self.client.bucket(self.bucket_name).blob(normalized)
        with start_span(
            "gcs.put",
            attributes={
                "gcs.bucket": self.bucket_name,
                "gcs.object": normalized,
            },
        ):
            _retry_external_call(
                operation=lambda: blob.upload_from_string(payload, content_type=content_type),
                failure_message=f"Failed to upload GCS blob '{normalized}'.",
                log_message="gcs.upload_failed_after_retries",
                log_context={
                    "bucket_name": self.bucket_name,
                    "object_name": normalized,
                },
            )
        return normalized

    def resolve_resource(self, logical_path: str) -> str:
        normalized = validate_logical_path(logical_path)
        return f"gs://{self.bucket_name}/{normalized}"

    def delete(self, logical_path: str) -> None:
        normalized = validate_logical_path(logical_path)
        with start_span(
            "gcs.delete",
            attributes={
                "gcs.bucket": self.bucket_name,
                "gcs.object": normalized,
            },
        ):
            try:
                self.client.bucket(self.bucket_name).blob(normalized).delete()
            except NotFound:
                return
            except Exception as exc:
                raise AdapterError(f"Failed to delete GCS blob '{normalized}'.") from exc
