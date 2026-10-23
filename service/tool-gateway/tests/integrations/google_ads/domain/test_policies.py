"""Test Google Ads query policy."""

import pytest

from tool_gateway.integrations.google_ads.domain.policies import require_select_gaql


def test_require_select_gaql_accepts_select_and_enforces_resources() -> None:
    """Accept SELECT queries only for allowlisted Google Ads resources."""
    assert require_select_gaql("SELECT campaign.id FROM campaign")
    assert require_select_gaql("SELECT campaign.id FROM campaign", {"campaign"})
    with pytest.raises(ValueError):
        require_select_gaql("UPDATE campaign SET name = 'x'")
    with pytest.raises(ValueError, match="resource is not allowed"):
        require_select_gaql(
            "SELECT customer_user_access.email_address FROM customer_user_access",
            {"campaign"},
        )


def test_require_select_gaql_normalizes_and_rejects_invalid_statements() -> None:
    """Remove one trailing semicolon and reject multiple or unscoped queries."""
    assert require_select_gaql(" SELECT campaign.id FROM campaign; ") == (
        "SELECT campaign.id FROM campaign"
    )
    with pytest.raises(ValueError, match="Multiple"):
        require_select_gaql("SELECT campaign.id FROM campaign; SELECT customer.id FROM customer")
    with pytest.raises(ValueError, match="resource"):
        require_select_gaql("SELECT 1", {"campaign"})
