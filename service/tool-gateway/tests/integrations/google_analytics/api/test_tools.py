"""Test the Google Analytics MCP registration contract."""

from support.mcp import registered_tool_names

from tool_gateway.integrations.google_analytics.api.tools import register_tools


def test_register_tools_exposes_google_analytics_operations() -> None:
    """Register the exact Google Analytics tool set."""
    assert registered_tool_names(register_tools) == {
        "google_analytics_run_report",
        "google_analytics_run_realtime_report",
        "google_analytics_get_metadata",
        "google_analytics_check_compatibility",
        "google_analytics_run_funnel_report",
        "google_analytics_admin_metadata",
    }
