"""Register the Google Ads MCP contract."""

from mcp.server.fastmcp import FastMCP

from tool_gateway.infrastructure.observability.audit import AuditRecorder
from tool_gateway.integrations.google_ads.application.service import GoogleAdsService


def register_tools(mcp: FastMCP, google_ads: GoogleAdsService, audit: AuditRecorder) -> None:
    """Register all Google Ads tools on an MCP server."""

    @mcp.tool()
    @audit.audited("google_ads_list_customers")
    def google_ads_list_customers() -> dict:
        """List accessible customers intersected with the allowlist."""
        return google_ads.list_customers()

    @mcp.tool()
    @audit.audited("google_ads_get_customer")
    def google_ads_get_customer(customer_id: str) -> dict:
        """Read one allowlisted customer."""
        return google_ads.get_customer(customer_id)

    @mcp.tool()
    @audit.audited("google_ads_readonly_query")
    def google_ads_readonly_query(
        customer_id: str, gaql: str, destination: str | None = None
    ) -> dict:
        """Run SELECT-only GAQL and optionally export it."""
        return google_ads.query(customer_id, gaql, destination)

    @mcp.tool()
    @audit.audited("google_ads_list_conversion_actions")
    def google_ads_list_conversion_actions(customer_id: str) -> dict:
        """List conversion actions."""
        return google_ads.list_conversion_actions(customer_id)

    @mcp.tool()
    @audit.audited("google_ads_get_change_history")
    def google_ads_get_change_history(customer_id: str, since: str, until: str) -> dict:
        """Read at most 30 days and 10,000 change events."""
        return google_ads.get_change_history(customer_id, since, until)
