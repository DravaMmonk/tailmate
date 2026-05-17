"""Shared exception types."""

from __future__ import annotations

from dataclasses import dataclass

from tailmate.contracts.types import ErrorDetail


@dataclass(slots=True)
class TailmateError(Exception):
    """Base exception for the application."""

    message: str
    code: int = 500
    error_type: str = "internal_error"

    def __str__(self) -> str:
        return self.message

    def to_error_detail(self) -> ErrorDetail:
        return {
            "code": self.code,
            "type": self.error_type,
            "message": self.message,
        }


class ConfigurationError(TailmateError):
    """Raised when configuration is invalid."""

    def __init__(self, message: str):
        super().__init__(message=message, code=500, error_type="configuration_error")


class SkillRegistrationError(TailmateError):
    """Raised when a skill contract is invalid or missing."""

    def __init__(self, message: str):
        super().__init__(message=message, code=500, error_type="skill_registration_error")


class AdapterError(TailmateError):
    """Raised when an adapter cannot reach an external dependency."""

    def __init__(self, message: str):
        super().__init__(message=message, code=503, error_type="adapter_error")


class DomainError(TailmateError):
    """Raised for user-visible business rule violations."""

    def __init__(self, message: str):
        super().__init__(message=message, code=400, error_type="domain_error")


class AuthenticationError(TailmateError):
    """Raised when request authentication is missing or invalid."""

    def __init__(self, message: str = "Authentication is required."):
        super().__init__(message=message, code=401, error_type="authentication_error")


class AuthorizationError(TailmateError):
    """Raised when an authenticated principal is not allowed to access a resource."""

    def __init__(self, message: str = "You are not allowed to access this resource."):
        super().__init__(message=message, code=403, error_type="authorization_error")


class NotFoundError(TailmateError):
    """Raised when the requested business resource does not exist."""

    def __init__(self, message: str = "The requested resource does not exist."):
        super().__init__(message=message, code=404, error_type="not_found_error")


class ConflictError(TailmateError):
    """Raised when the requested mutation conflicts with existing state."""

    def __init__(self, message: str = "The requested operation conflicts with existing state."):
        super().__init__(message=message, code=409, error_type="conflict_error")


class UnsupportedMediaTypeError(DomainError):
    """Raised when a media payload type is not supported."""

    def __init__(self, content_type: str):
        super().__init__(f"Unsupported media content type '{content_type}'.")
        self.code = 415
        self.error_type = "unsupported_media_type"


class MediaProcessingError(AdapterError):
    """Raised when media sanitization or storage fails."""

    def __init__(self, message: str):
        super().__init__(message=message)
        self.error_type = "media_processing_error"


class MediaAssetPersistenceError(AdapterError):
    """Raised when sanitized media cannot be durably tracked."""

    def __init__(self, message: str):
        super().__init__(message=message)
        self.error_type = "media_asset_persistence_error"


class InternalError(TailmateError):
    """Raised when an unexpected internal failure occurs."""

    def __init__(self, message: str = "An unexpected internal error occurred."):
        super().__init__(message=message, code=500, error_type="internal_error")
