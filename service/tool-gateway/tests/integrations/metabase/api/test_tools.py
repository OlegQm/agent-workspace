"""Test the Metabase MCP registration contract."""

from support.mcp import registered_tool_names

from tool_gateway.integrations.metabase.api.tools import register_tools


def test_register_tools_exposes_metabase_operations() -> None:
    """Register the exact Metabase tool set."""
    assert registered_tool_names(register_tools) == {
        "metabase_search",
        "metabase_get_question",
        "metabase_get_dashboard",
        "metabase_run_question",
        "metabase_export_question",
        "metabase_readonly_query",
        "metabase_list_collections",
        "metabase_list_collection_items",
        "metabase_get_database_metadata",
        "metabase_get_table_metadata",
        "metabase_get_field_metadata",
        "metabase_list_dashboard_subscriptions",
        "metabase_get_collection_permissions",
        "metabase_get_safe_settings",
    }
