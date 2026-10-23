"""Test the BigQuery MCP registration contract."""

from support.mcp import registered_tool_names

from tool_gateway.integrations.bigquery.api.tools import register_tools


def test_register_tools_exposes_bigquery_operations() -> None:
    """Register the exact BigQuery tool set."""
    assert registered_tool_names(register_tools) == {
        "bigquery_list_datasets",
        "bigquery_get_dataset",
        "bigquery_list_tables",
        "bigquery_get_table",
        "bigquery_list_partitions",
        "bigquery_dry_run",
        "bigquery_readonly_query",
    }
