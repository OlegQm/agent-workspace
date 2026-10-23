"""Register the Meta Ads MCP contract."""

from mcp.server.fastmcp import FastMCP

from tool_gateway.infrastructure.observability.audit import AuditRecorder
from tool_gateway.integrations.meta_ads.application.service import MetaAdsService


def register_tools(mcp: FastMCP, meta_ads: MetaAdsService, audit: AuditRecorder) -> None:
    """Register all Meta Ads tools on an MCP server."""

    @mcp.tool()
    @audit.audited("meta_ads_get_account")
    async def meta_ads_get_account(account_id: str) -> dict:
        """Read allowlisted account details."""
        return await meta_ads.get_account(account_id)

    @mcp.tool()
    @audit.audited("meta_ads_list_objects")
    async def meta_ads_list_objects(
        account_id: str, object_type: str, fields: list[str] | None = None
    ) -> dict:
        """List campaigns, ad sets, ads or creatives through an account."""
        return await meta_ads.list_objects(account_id, object_type, fields)

    @mcp.tool()
    @audit.audited("meta_ads_account_activity")
    async def meta_ads_account_activity(account_id: str, since: str, until: str) -> dict:
        """Read account activity when available."""
        return await meta_ads.activities(account_id, since, until)

    @mcp.tool()
    @audit.audited("meta_ads_insights")
    async def meta_ads_insights(
        account_id: str,
        since: str,
        until: str,
        level: str = "campaign",
        fields: list[str] | None = None,
        breakdowns: list[str] | None = None,
        action_breakdowns: list[str] | None = None,
        time_increment: str = "all_days",
        action_attribution_windows: list[str] | None = None,
        filtering: list[dict] | None = None,
    ) -> dict:
        """Read bounded insights with fixed fields and breakdowns."""
        return await meta_ads.insights(
            account_id,
            since,
            until,
            level,
            fields or ["campaign_id", "campaign_name", "impressions", "clicks", "spend"],
            breakdowns,
            action_breakdowns,
            time_increment,
            action_attribution_windows,
            filtering,
        )
