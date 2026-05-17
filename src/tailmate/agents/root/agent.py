"""Deployable custom agent class for Vertex AI Agent Engine."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from tailmate.agent_runtime.current_context import (
    RuntimeRequestContext,
    reset_current_context,
    set_current_context,
)
from tailmate.agent_runtime.services.graph_orchestrator import GraphOrchestrator
from tailmate.bootstrap.config import AppConfig
from tailmate.contracts.constants import (
    DOG_PROFILE_RESULT_METADATA_KEY,
    STRIP_METADATA_REQUEST_METADATA_KEY,
    STRIP_METADATA_RESULT_METADATA_KEY,
    TURN_DEBUG_METADATA_KEY,
)
from tailmate.contracts.errors import TailmateError, InternalError
from tailmate.contracts.types import QueryInput, QueryOutput, normalize_query_input
from tailmate.observability import (
    LogContext,
    generate_request_id,
    generate_trace_id,
    reset_log_context,
    set_log_context,
)


@dataclass
class RootAgent:
    """Custom agent class following the Agent Engine lifecycle contract."""

    config: AppConfig
    orchestrator: GraphOrchestrator | None = field(default=None, init=False)

    @property
    def name(self) -> str:
        return self.config.agent_name

    def set_up(self) -> None:
        """Runtime-only initialization hook."""

        from tailmate.bootstrap.container import AppContainer

        container = AppContainer(config=self.config)
        self.orchestrator = container.build_orchestrator()

    @staticmethod
    def _stream_text_chunks(text: str, *, chunk_size: int = 120) -> Iterator[str]:
        """Yield stable text chunks for SSE transport without altering content."""

        if not text:
            return
        for index in range(0, len(text), chunk_size):
            yield text[index : index + chunk_size]

    @staticmethod
    def _build_fallback_query_output(
        context: Any,
        *,
        request_metadata: Mapping[str, Any] | None = None,
    ) -> QueryOutput:
        """Build a canonical query output for orchestrator stubs without helper methods."""

        request_metadata = dict(request_metadata or {})
        context_attributes = getattr(context, "attributes", {})
        if not isinstance(context_attributes, Mapping):
            context_attributes = {}
        turns = getattr(context, "turns", [])
        if not isinstance(turns, list):
            turns = []

        response = str(context_attributes.get("last_response", ""))
        resolved_dog_id = context_attributes.get("dog_id", request_metadata.get("dog_id"))
        response_metadata: dict[str, Any] = {
            "turn_count": len(turns),
            "dog_id": resolved_dog_id,
        }
        dog_profile_result = context_attributes.get(DOG_PROFILE_RESULT_METADATA_KEY)
        if isinstance(dog_profile_result, Mapping):
            response_metadata[DOG_PROFILE_RESULT_METADATA_KEY] = dict(dog_profile_result)
        strip_metadata_requested = STRIP_METADATA_REQUEST_METADATA_KEY in request_metadata
        if strip_metadata_requested:
            strip_metadata_result = context_attributes.get(STRIP_METADATA_RESULT_METADATA_KEY)
            if isinstance(strip_metadata_result, Mapping):
                response_metadata[STRIP_METADATA_RESULT_METADATA_KEY] = dict(strip_metadata_result)
        turn_debug = context_attributes.get(TURN_DEBUG_METADATA_KEY)
        if isinstance(turn_debug, Mapping):
            response_metadata[TURN_DEBUG_METADATA_KEY] = dict(turn_debug)
        return {
            "session_id": str(getattr(context, "session_id", request_metadata.get("session_id", ""))),
            "response": response,
            "metadata": response_metadata,
            "error": None,
        }

    def _build_query_output(self, context: Any, *, request_metadata: Mapping[str, Any]) -> QueryOutput:
        """Build the canonical query output using the orchestrator helper when available."""

        if self.orchestrator is not None:
            build_query_output = getattr(self.orchestrator, "build_query_output", None)
            if callable(build_query_output):
                return build_query_output(context, request_metadata=dict(request_metadata))
        return self._build_fallback_query_output(context, request_metadata=request_metadata)

    def _execute_query(self, payload: QueryInput) -> QueryOutput:
        """Run the orchestrator and assemble the canonical query response."""

        metadata = dict(payload.get("metadata", {}))
        request_id = str(metadata.get("request_id", "")).strip() or generate_request_id()
        trace_id = str(metadata.get("trace_id", "")).strip() or generate_trace_id()
        metadata["request_id"] = request_id
        metadata["trace_id"] = trace_id
        token = set_current_context(
            RuntimeRequestContext(
                session_id=payload["session_id"],
                metadata=metadata,
                dog_id=metadata.get("dog_id"),
                user_id=metadata.get("user_id"),
                request_id=request_id,
                trace_id=trace_id,
            )
        )
        log_token = set_log_context(
            LogContext(
                request_id=request_id,
                trace_id=trace_id,
                user_id=str(metadata.get("user_id", "")).strip() or None,
                session_id=payload["session_id"],
            )
        )
        try:
            if self.orchestrator is None:
                raise InternalError("RootAgent.set_up() must be called before query().")
            context = self.orchestrator.run(payload["session_id"], payload["message"])
            return self._build_query_output(context, request_metadata=metadata)
        except TailmateError as exc:
            return {
                "session_id": payload["session_id"],
                "response": "",
                "metadata": {"dog_id": metadata.get("dog_id")},
                "error": exc.to_error_detail(),
            }
        except Exception:
            error = InternalError()
            return {
                "session_id": payload["session_id"],
                "response": "",
                "metadata": {"dog_id": metadata.get("dog_id")},
                "error": error.to_error_detail(),
            }
        finally:
            reset_log_context(log_token)
            reset_current_context(token)

    def query(self, input: QueryInput | None = None, **kwargs: object) -> QueryOutput:
        """Handles a non-streaming query."""

        raw_session_id = ""
        if input is not None:
            raw_session_id = str(input.get("session_id", ""))
        if not raw_session_id and "session_id" in kwargs:
            raw_session_id = str(kwargs["session_id"])

        try:
            payload = normalize_query_input(input, **kwargs)
        except Exception:
            error = InternalError("Invalid query input.")
            return {
                "session_id": raw_session_id or "unknown-session",
                "response": "",
                "metadata": {},
                "error": error.to_error_detail(),
            }

        return self._execute_query(payload)

    def stream_query(self, input: QueryInput | None = None, **kwargs: object) -> Iterator[dict[str, object]]:
        """Handles a streaming query with SSE-friendly event objects."""

        raw_session_id = ""
        if input is not None:
            raw_session_id = str(input.get("session_id", ""))
        if not raw_session_id and "session_id" in kwargs:
            raw_session_id = str(kwargs["session_id"])

        try:
            payload = normalize_query_input(input, **kwargs)
        except Exception:
            error = InternalError("Invalid query input.")
            yield {
                "event": "query.completed",
                "output": {
                    "session_id": raw_session_id or "unknown-session",
                    "response": "",
                    "metadata": {},
                    "error": error.to_error_detail(),
                },
            }
            return

        metadata = dict(payload.get("metadata", {}))
        request_id = str(metadata.get("request_id", "")).strip() or generate_request_id()
        trace_id = str(metadata.get("trace_id", "")).strip() or generate_trace_id()
        metadata["request_id"] = request_id
        metadata["trace_id"] = trace_id
        token = set_current_context(
            RuntimeRequestContext(
                session_id=payload["session_id"],
                metadata=metadata,
                dog_id=metadata.get("dog_id"),
                user_id=metadata.get("user_id"),
                request_id=request_id,
                trace_id=trace_id,
            )
        )
        log_token = set_log_context(
            LogContext(
                request_id=request_id,
                trace_id=trace_id,
                user_id=str(metadata.get("user_id", "")).strip() or None,
                session_id=payload["session_id"],
            )
        )
        try:
            yield {
                "event": "query.started",
                "session_id": payload["session_id"],
            }
            if self.orchestrator is None:
                error = InternalError("RootAgent.set_up() must be called before query().")
                yield {
                    "event": "query.completed",
                    "session_id": payload["session_id"],
                    "output": {
                        "session_id": payload["session_id"],
                        "response": "",
                        "metadata": {"dog_id": metadata.get("dog_id")},
                        "error": error.to_error_detail(),
                    },
                }
                return
            stream_run = getattr(self.orchestrator, "stream_run", None)
            if callable(stream_run):
                yield from stream_run(payload["session_id"], payload["message"])
                return

            context = self.orchestrator.run(payload["session_id"], payload["message"])
            output = self._build_query_output(context, request_metadata=metadata)
            for chunk in self._stream_text_chunks(output["response"]):
                yield {
                    "event": "query.delta",
                    "session_id": output["session_id"],
                    "delta": chunk,
                }
            yield {
                "event": "query.completed",
                "session_id": output["session_id"],
                "output": output,
            }
        except TailmateError as exc:
            yield {
                "event": "query.completed",
                "session_id": payload["session_id"],
                "output": {
                    "session_id": payload["session_id"],
                    "response": "",
                    "metadata": {"dog_id": metadata.get("dog_id")},
                    "error": exc.to_error_detail(),
                },
            }
        except Exception:
            error = InternalError()
            yield {
                "event": "query.completed",
                "session_id": payload["session_id"],
                "output": {
                    "session_id": payload["session_id"],
                    "response": "",
                    "metadata": {"dog_id": metadata.get("dog_id")},
                    "error": error.to_error_detail(),
                },
            }
        finally:
            reset_log_context(log_token)
            reset_current_context(token)
