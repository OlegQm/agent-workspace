"""Test the Meta Ads MCP registration contract."""

from support.mcp import registered_tool_names

from tool_gateway.integrations.meta_ads.api.tools import register_tools


def test_register_tools_exposes_meta_ads_operations() -> None:
    """Register the exact Meta Ads tool set."""
    assert registered_tool_names(register_tools) == {
        "meta_ads_get_account",
        "meta_ads_list_objects",
        "meta_ads_account_activity",
        "meta_ads_insights",
    }
