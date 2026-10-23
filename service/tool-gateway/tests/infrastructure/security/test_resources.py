"""Test shared integration resource allowlists."""

import pytest

from tool_gateway.infrastructure.security.resources import require_allowed, require_allowed_exact


def test_allowlist_helpers_normalize_or_match_exact_values() -> None:
    """Return allowed values and reject identifiers outside the role scope."""
    assert require_allowed("act_123-456", ["123456"], "account") == "123456"
    with pytest.raises(ValueError, match="not allowed"):
        require_allowed("999", ["123"], "account")
    assert require_allowed_exact(7, [7], "database") == 7
    with pytest.raises(ValueError, match="not allowed"):
        require_allowed_exact(8, [7], "database")
