"""HTTP client for the Cloud Run database gateway."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2 import id_token
import requests

from tailmate.agent_runtime.current_context import get_current_context, get_current_user_id
from tailmate.contracts.constants import REQUEST_ID_HEADER, TRACE_ID_HEADER, TRUSTED_USER_ID_HEADER
from tailmate.contracts.errors import AdapterError, DomainError
from tailmate.observability import get_log_context
from tailmate.tracing import inject_trace_context, start_span


@dataclass
class DbGatewayClient:
    """Calls the Cloud Run gateway with an ID-token-authenticated session."""

    gateway_url: str
    timeout_seconds: int = 30
    session: requests.Session | None = None
    _authorized_session: requests.Session | None = field(default=None, init=False, repr=False)

    @property
    def base_url(self) -> str:
        return self.gateway_url.rstrip("/")

    def _build_authorized_session(self) -> requests.Session:
        auth_request = Request()
        credentials = id_token.fetch_id_token_credentials(self.base_url, request=auth_request)
        return AuthorizedSession(credentials, auth_request=auth_request)

    def _get_session(self) -> requests.Session:
        if self.session is not None:
            return self.session
        if self._authorized_session is None:
            self._authorized_session = self._build_authorized_session()
        return self._authorized_session

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        form_data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        resolved_headers = self._build_correlation_headers()
        if headers:
            resolved_headers.update(headers)
        inject_trace_context(resolved_headers)
        request_kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "timeout": self.timeout_seconds,
        }
        if resolved_headers:
            request_kwargs["headers"] = resolved_headers
        if files is None:
            request_kwargs["json"] = payload
        else:
            request_kwargs["data"] = form_data or {}
            request_kwargs["files"] = files
        try:
            with start_span(
                f"db_gateway.{method.lower()}",
                attributes={
                    "http.method": method.upper(),
                    "http.url": url,
                    "tailmate.db_gateway.path": path,
                },
            ):
                response = self._get_session().request(**request_kwargs)
                try:
                    response.raise_for_status()
                except requests.HTTPError as exc:
                    message = self._extract_error_message(response)
                    raise AdapterError(
                        f"Database gateway request failed with status {response.status_code}: {message}"
                    ) from exc
                data = response.json()
        except requests.RequestException as exc:
            raise AdapterError(f"Failed to reach database gateway at '{url}'.") from exc
        except ValueError as exc:
            raise AdapterError("Database gateway returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise AdapterError("Database gateway returned an unexpected payload shape.")
        return data

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text.strip() or response.reason or "unknown error"
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, str) and error.strip():
                return error.strip()
        return response.text.strip() or response.reason or "unknown error"

    @staticmethod
    def _resolve_session_id(explicit_session_id: str | None = None) -> str | None:
        if explicit_session_id is not None and explicit_session_id.strip():
            return explicit_session_id.strip()

        current_context = get_current_context()
        if current_context is None:
            return None
        session_id = current_context.session_id.strip()
        return session_id or None

    @staticmethod
    def _build_trusted_user_headers(explicit_user_id: str | None = None) -> dict[str, str]:
        trusted_user_id = (explicit_user_id or get_current_user_id() or "").strip()
        if not trusted_user_id:
            raise DomainError("Missing verified user_id for database gateway request.")
        return {TRUSTED_USER_ID_HEADER: trusted_user_id}

    @staticmethod
    def _build_correlation_headers() -> dict[str, str]:
        log_context = get_log_context()
        headers: dict[str, str] = {}
        request_id = (log_context.request_id or "").strip()
        trace_id = (log_context.trace_id or "").strip()
        if request_id:
            headers[REQUEST_ID_HEADER] = request_id
        if trace_id:
            headers[TRACE_ID_HEADER] = trace_id
        return headers

    def load_session(self, session_id: str) -> dict[str, Any]:
        session_path = quote(session_id, safe="")
        return self._request_json("GET", f"/sessions/{session_path}")

    def save_session(
        self,
        session_id: str,
        *,
        turns: list[dict[str, Any]],
        attributes: dict[str, Any],
    ) -> None:
        session_path = quote(session_id, safe="")
        self._request_json(
            "PUT",
            f"/sessions/{session_path}",
            payload={
                "turns": turns,
                "attributes": attributes,
            },
        )

    def ensure_platform_user(
        self,
        *,
        platform: str,
        platform_user_id: str,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/bridge/users/ensure",
            payload={
                "platform": platform,
                "platform_user_id": platform_user_id,
            },
        )

    def claim_webhook_event(self, *, message_id: str) -> bool:
        payload = self._request_json(
            "POST",
            "/bridge/webhooks/claim",
            payload={"message_id": message_id},
        )
        return bool(payload.get("claimed"))

    def release_webhook_event(self, *, message_id: str) -> bool:
        payload = self._request_json(
            "POST",
            "/bridge/webhooks/release",
            payload={"message_id": message_id},
        )
        return bool(payload.get("released"))

    def bridge_query(
        self,
        *,
        platform: str,
        platform_user_id: str,
        message: str,
        session_id: str | None = None,
        dog_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "platform": platform,
            "platform_user_id": platform_user_id,
            "message": message,
        }
        resolved_session_id = self._resolve_session_id(session_id)
        if resolved_session_id:
            payload["session_id"] = resolved_session_id
        if dog_id is not None and dog_id.strip():
            payload["dog_id"] = dog_id.strip()
        return self._request_json("POST", "/bridge/query", payload=payload)

    def upload_media(
        self,
        *,
        dog_id: str,
        resource_kind: str,
        filename: str,
        content_type: str,
        payload: bytes,
        session_id: str | None = None,
        trusted_user_id: str | None = None,
    ) -> dict[str, Any]:
        form_data = {
            "dog_id": dog_id,
            "resource_kind": resource_kind,
        }
        resolved_session_id = self._resolve_session_id(session_id)
        if resolved_session_id:
            form_data["session_id"] = resolved_session_id
        return self._request_json(
            "POST",
            "/media/upload",
            form_data=form_data,
            files={
                "file": (filename, payload, content_type),
            },
            headers=self._build_trusted_user_headers(trusted_user_id),
        )

    def create_dog_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        explicit_user_id = str(payload.get("user_id", "")).strip()
        return self._request_json(
            "POST",
            "/dog-profiles",
            payload=payload,
            headers=self._build_trusted_user_headers(explicit_user_id),
        )

    def load_dog_profile(
        self,
        dog_id: str,
        *,
        trusted_user_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        dog_path = quote(dog_id, safe="")
        path = f"/dog-profiles/{dog_path}"
        resolved_session_id = self._resolve_session_id(session_id)
        if resolved_session_id:
            path = f"{path}?session_id={quote(resolved_session_id, safe='')}"
        payload = self._request_json(
            "GET",
            path,
            headers=self._build_trusted_user_headers(trusted_user_id),
        )
        if payload.get("found") is False:
            return None
        profile = payload.get("profile")
        if isinstance(profile, dict):
            return profile
        return payload

    def list_dog_profiles(
        self,
        *,
        trusted_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        payload = self._request_json(
            "GET",
            "/dog-profiles",
            headers=self._build_trusted_user_headers(trusted_user_id),
        )
        profiles = payload.get("profiles")
        if not isinstance(profiles, list):
            raise AdapterError("Database gateway returned an unexpected dog profile list.")
        normalized_profiles: list[dict[str, Any]] = []
        for profile in profiles:
            if not isinstance(profile, dict):
                raise AdapterError("Database gateway returned an unexpected dog profile payload.")
            normalized_profiles.append(profile)
        return normalized_profiles

    def enrich_dog_profile(
        self,
        dog_id: str,
        payload: dict[str, Any],
        *,
        trusted_user_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        dog_path = quote(dog_id, safe="")
        normalized_payload = dict(payload)
        resolved_session_id = self._resolve_session_id(session_id)
        if resolved_session_id:
            normalized_payload["session_id"] = resolved_session_id
        return self._request_json(
            "POST",
            f"/dog-profiles/{dog_path}/enrich",
            payload=normalized_payload,
            headers=self._build_trusted_user_headers(trusted_user_id),
        )

    def search_knowledge(
        self,
        *,
        embedding: list[float],
        locale: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        payload = self._request_json(
            "POST",
            "/knowledge/search",
            payload={
                "embedding": embedding,
                "locale": locale,
                "top_k": top_k,
            },
        )
        hits = payload.get("hits")
        if not isinstance(hits, list):
            raise AdapterError("Database gateway returned an unexpected knowledge payload shape.")
        return hits
