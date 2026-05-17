"""Shared authorization helpers."""

from __future__ import annotations

from tailmate.contracts.errors import AuthorizationError


def assert_owner(
    resource_user_id: str,
    requesting_user_id: str,
    *,
    resource_label: str = "resource",
) -> None:
    """Raise when a caller does not own the requested resource."""

    normalized_resource_user_id = resource_user_id.strip()
    normalized_requesting_user_id = requesting_user_id.strip()
    if normalized_resource_user_id != normalized_requesting_user_id:
        raise AuthorizationError(f"User does not own {resource_label}.")
