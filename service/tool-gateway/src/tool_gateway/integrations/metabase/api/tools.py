"""Register the Metabase MCP contract."""

from mcp.server.fastmcp import FastMCP

from tool_gateway.infrastructure.observability.audit import AuditRecorder
from tool_gateway.integrations.metabase.application.service import MetabaseService


def register_tools(mcp: FastMCP, metabase: MetabaseService, audit: AuditRecorder) -> None:
    """Register all Metabase tools on an MCP server."""

    @mcp.tool()
    @audit.audited("metabase_search")
    async def metabase_search(query: str, models: list[str] | None = None) -> dict:
        """Search accessible PROD questions and dashboards."""
        return await metabase.search(query, models)

    @mcp.tool()
    @audit.audited("metabase_get_question")
    async def metabase_get_question(question_id: int) -> dict:
        """Read one accessible PROD question."""
        return await metabase.get_card(question_id)

    @mcp.tool()
    @audit.audited("metabase_get_dashboard")
    async def metabase_get_dashboard(dashboard_id: int) -> dict:
        """Read one accessible PROD dashboard."""
        return await metabase.get_dashboard(dashboard_id)

    @mcp.tool()
    @audit.audited("metabase_run_question")
    async def metabase_run_question(question_id: int, parameters: list[dict] | None = None) -> dict:
        """Execute an accessible PROD question without modifying it."""
        return await metabase.run_card(question_id, parameters)

    @mcp.tool()
    @audit.audited("metabase_export_question")
    async def metabase_export_question(
        question_id: int,
        destination: str,
        parameters: list[dict] | None = None,
        export_format: str = "csv",
    ) -> dict:
        """Export an accessible question into the agent workspace."""
        return await metabase.export_card(question_id, destination, parameters, export_format)

    @mcp.tool()
    @audit.audited("metabase_readonly_query")
    async def metabase_readonly_query(database_id: int, sql: str) -> dict:
        """Run one SELECT/WITH query on an allowlisted database."""
        return await metabase.query(database_id, sql)

    @mcp.tool()
    @audit.audited("metabase_list_collections")
    async def metabase_list_collections(parent_id: int | None = None) -> dict:
        """List allowlisted collections."""
        return await metabase.list_collections(parent_id)

    @mcp.tool()
    @audit.audited("metabase_list_collection_items")
    async def metabase_list_collection_items(
        collection_id: int, models: list[str] | None = None
    ) -> dict:
        """List items in an allowlisted collection."""
        return await metabase.list_collection_items(collection_id, models)

    @mcp.tool()
    @audit.audited("metabase_get_database_metadata")
    async def metabase_get_database_metadata(database_id: int) -> dict:
        """Read allowlisted database metadata."""
        return await metabase.get_database_metadata(database_id)

    @mcp.tool()
    @audit.audited("metabase_get_table_metadata")
    async def metabase_get_table_metadata(table_id: int) -> dict:
        """Read table metadata after ownership validation."""
        return await metabase.get_table_metadata(table_id)

    @mcp.tool()
    @audit.audited("metabase_get_field_metadata")
    async def metabase_get_field_metadata(field_id: int) -> dict:
        """Read field metadata after ownership validation."""
        return await metabase.get_field_metadata(field_id)

    @mcp.tool()
    @audit.audited("metabase_list_dashboard_subscriptions")
    async def metabase_list_dashboard_subscriptions(dashboard_id: int) -> dict:
        """List subscriptions for an accessible dashboard."""
        return await metabase.list_dashboard_subscriptions(dashboard_id)

    @mcp.tool()
    @audit.audited("metabase_get_collection_permissions")
    async def metabase_get_collection_permissions(collection_id: int) -> dict:
        """Read permissions for an allowlisted collection."""
        return await metabase.get_collection_permissions(collection_id)

    @mcp.tool()
    @audit.audited("metabase_get_safe_settings")
    async def metabase_get_safe_settings() -> dict:
        """Read explicitly allowlisted non-secret settings."""
        return await metabase.get_safe_settings()
