from __future__ import annotations

import pytest

from tailmate.contracts.authz import assert_owner
from tailmate.contracts.errors import AuthorizationError


def test_assert_owner_allows_matching_owner_ids() -> None:
    assert_owner("user-1", "user-1", resource_label="dog profile")


def test_assert_owner_rejects_mismatched_owner_ids() -> None:
    with pytest.raises(AuthorizationError, match="User does not own dog profile."):
        assert_owner("user-1", "user-2", resource_label="dog profile")
