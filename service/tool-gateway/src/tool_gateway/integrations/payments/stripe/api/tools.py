"""Register the Stripe MCP contract."""

from mcp.server.fastmcp import FastMCP

from tool_gateway.infrastructure.observability.audit import AuditRecorder
from tool_gateway.integrations.payments.stripe.application.service import StripeService


def register_tools(mcp: FastMCP, stripe: StripeService, audit: AuditRecorder) -> None:
    """Register all Stripe tools on an MCP server."""

    @mcp.tool()
    @audit.audited("stripe_list_objects")
    async def stripe_list_objects(
        account: str,
        object_type: str,
        created_from: int | None = None,
        created_to: int | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> dict:
        """List PaymentIntents, Charges or Refunds."""
        return await stripe.list_objects(
            account, object_type, created_from, created_to, status, limit
        )

    @mcp.tool()
    @audit.audited("stripe_get_object")
    async def stripe_get_object(account: str, object_type: str, object_id: str) -> dict:
        """Read one payment, charge, refund or balance transaction."""
        return await stripe.get_object(account, object_type, object_id)
