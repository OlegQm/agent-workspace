"""Test the Google Ads MCP registration contract."""

from support.mcp import registered_tool_names

from tool_gateway.integrations.google_ads.api.tools import register_tools


def test_register_tools_exposes_google_ads_operations() -> None:
    """Register the exact Google Ads tool set."""
    assert registered_tool_names(register_tools) == {
        "google_ads_list_customers",
        "google_ads_get_customer",
        "google_ads_readonly_query",
        "google_ads_list_conversion_actions",
        "google_ads_get_change_history",
    }
