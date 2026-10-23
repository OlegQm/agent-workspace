"""Register the BigQuery MCP contract."""

from mcp.server.fastmcp import FastMCP

from tool_gateway.infrastructure.observability.audit import AuditRecorder
from tool_gateway.integrations.bigquery.application.service import BigQueryService


def register_tools(mcp: FastMCP, bigquery: BigQueryService, audit: AuditRecorder) -> None:
    """Register all BigQuery tools on an MCP server."""

    @mcp.tool()
    @audit.audited("bigquery_list_datasets")
    def bigquery_list_datasets() -> list[dict]:
        """List allowlisted PROD datasets."""
        return bigquery.list_datasets()

    @mcp.tool()
    @audit.audited("bigquery_get_dataset")
    def bigquery_get_dataset(dataset: str) -> dict:
        """Read allowlisted dataset metadata."""
        return bigquery.get_dataset(dataset)

    @mcp.tool()
    @audit.audited("bigquery_list_tables")
    def bigquery_list_tables(dataset: str) -> list[dict]:
        """List tables in an allowlisted dataset."""
        return bigquery.list_tables(dataset)

    @mcp.tool()
    @audit.audited("bigquery_get_table")
    def bigquery_get_table(dataset: str, table: str) -> dict:
        """Read table schema, partitioning, labels and timestamps."""
        return bigquery.get_table(dataset, table)

    @mcp.tool()
    @audit.audited("bigquery_list_partitions")
    def bigquery_list_partitions(dataset: str, table: str) -> dict:
        """List partitions of an allowlisted table."""
        return bigquery.list_partitions(dataset, table)

    @mcp.tool()
    @audit.audited("bigquery_dry_run")
    def bigquery_dry_run(sql: str) -> dict:
        """Validate query datasets and estimate bytes."""
        return bigquery.dry_run(sql)

    @mcp.tool()
    @audit.audited("bigquery_readonly_query")
    def bigquery_readonly_query(sql: str, destination: str | None = None) -> dict:
        """Run one bounded SELECT/WITH and optionally export CSV/JSON."""
        return bigquery.query(sql, destination)
