"""Register the Google Analytics MCP contract."""

from mcp.server.fastmcp import FastMCP

from tool_gateway.infrastructure.observability.audit import AuditRecorder
from tool_gateway.integrations.google_analytics.application.service import GoogleAnalyticsService


def register_tools(
    mcp: FastMCP, google_analytics: GoogleAnalyticsService, audit: AuditRecorder
) -> None:
    """Register all Google Analytics tools on an MCP server."""

    @mcp.tool()
    @audit.audited("google_analytics_run_report")
    def google_analytics_run_report(
        property_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        dimensions: list[str] | None = None,
        metrics: list[str] | None = None,
        limit: int = 10_000,
        date_ranges: list[dict] | None = None,
        dimension_filter: dict | None = None,
        metric_filter: dict | None = None,
        order_bys: list[dict] | None = None,
        offset: int = 0,
        destination: str | None = None,
    ) -> dict:
        """Run a PROD report with ranges, filters, ordering and export."""
        return google_analytics.run_report(
            property_id,
            start_date,
            end_date,
            dimensions,
            metrics,
            limit,
            date_ranges,
            dimension_filter,
            metric_filter,
            order_bys,
            offset,
            destination,
        )

    @mcp.tool()
    @audit.audited("google_analytics_run_realtime_report")
    def google_analytics_run_realtime_report(
        property_id: str, dimensions: list[str], metrics: list[str], limit: int = 10_000
    ) -> dict:
        """Run a bounded realtime report."""
        return google_analytics.run_realtime_report(property_id, dimensions, metrics, limit)

    @mcp.tool()
    @audit.audited("google_analytics_get_metadata")
    def google_analytics_get_metadata(property_id: str) -> dict:
        """Read dimensions and metrics metadata."""
        return google_analytics.get_metadata(property_id)

    @mcp.tool()
    @audit.audited("google_analytics_check_compatibility")
    def google_analytics_check_compatibility(
        property_id: str,
        dimensions: list[str],
        metrics: list[str],
        dimension_filter: dict | None = None,
        metric_filter: dict | None = None,
    ) -> dict:
        """Check whether dimensions and metrics can be used together."""
        return google_analytics.check_compatibility(
            property_id, dimensions, metrics, dimension_filter, metric_filter
        )

    @mcp.tool()
    @audit.audited("google_analytics_run_funnel_report")
    def google_analytics_run_funnel_report(
        property_id: str,
        start_date: str,
        end_date: str,
        steps: list[dict],
        open_funnel: bool = False,
        breakdown_dimension: str | None = None,
        next_action_dimension: str | None = None,
        limit: int = 10_000,
    ) -> dict:
        """Run a bounded v1alpha funnel report."""
        return google_analytics.run_funnel_report(
            property_id,
            start_date,
            end_date,
            steps,
            open_funnel,
            breakdown_dimension,
            next_action_dimension,
            limit,
        )

    @mcp.tool()
    @audit.audited("google_analytics_admin_metadata")
    def google_analytics_admin_metadata(property_id: str, resource: str) -> dict:
        """Get/list property configuration through Admin API."""
        return google_analytics.admin_metadata(property_id, resource)
