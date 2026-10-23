"""Register the GoPay MCP contract."""

from mcp.server.fastmcp import FastMCP

from tool_gateway.infrastructure.observability.audit import AuditRecorder
from tool_gateway.integrations.payments.gopay.application.service import GoPayService


def register_tools(mcp: FastMCP, gopay: GoPayService, audit: AuditRecorder) -> None:
    """Register all GoPay tools on an MCP server."""

    @mcp.tool()
    @audit.audited("gopay_get_payment")
    async def gopay_get_payment(account: str, payment_id: str) -> dict:
        """Read one explicit GoPay payment ID."""
        return await gopay.get_payment(account, payment_id)

    @mcp.tool()
    @audit.audited("gopay_get_payments")
    async def gopay_get_payments(account: str, payment_ids: list[str]) -> dict:
        """Read up to 100 explicit GoPay payment IDs."""
        return await gopay.get_payments(account, payment_ids)
