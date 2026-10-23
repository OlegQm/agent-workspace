"""Test required integration credential primitives."""

import pytest

from tool_gateway.infrastructure.security.credentials import require_config


def test_require_config_rejects_missing_values() -> None:
    """Return present values and fail closed when configuration is absent."""
    assert require_config("value", "Field") == "value"
    with pytest.raises(RuntimeError, match="Field is not configured"):
        require_config("", "Field")
