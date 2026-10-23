"""Register the SuperFaktura MCP contract."""

from mcp.server.fastmcp import FastMCP

from tool_gateway.infrastructure.observability.audit import AuditRecorder
from tool_gateway.integrations.superfaktura.application.service import SuperFakturaService


def register_tools(mcp: FastMCP, superfaktura: SuperFakturaService, audit: AuditRecorder) -> None:
    """Register all SuperFaktura tools on an MCP server."""

    @mcp.tool()
    @audit.audited("superfaktura_list_companies")
    def superfaktura_list_companies() -> dict:
        """List allowlisted company aliases and safe display names."""
        return superfaktura.list_companies()

    @mcp.tool()
    @audit.audited("superfaktura_list_invoices")
    async def superfaktura_list_invoices(
        page: int = 1,
        invoice_type: str = "regular",
        company: str = "default",
        created_from: str | None = None,
        created_to: str | None = None,
        status: str | None = None,
        destination: str | None = None,
    ) -> dict:
        """List invoices for a company alias from superfaktura_list_companies."""
        return await superfaktura.list_invoices(
            company, page, invoice_type, created_from, created_to, status, destination
        )

    @mcp.tool()
    @audit.audited("superfaktura_get_invoice")
    async def superfaktura_get_invoice(
        invoice_id: int,
        company: str = "default",
        include_client: bool = False,
        include_notes: bool = False,
    ) -> dict:
        """Read one normalized invoice with optional identity and free-text details."""
        return await superfaktura.get_invoice(invoice_id, company, include_client, include_notes)

    @mcp.tool()
    @audit.audited("superfaktura_get_invoice_payments")
    async def superfaktura_get_invoice_payments(invoice_id: int, company: str = "default") -> dict:
        """Read payment information embedded in an invoice."""
        return await superfaktura.get_invoice_payments(invoice_id, company)

    @mcp.tool()
    @audit.audited("superfaktura_list_clients")
    async def superfaktura_list_clients(
        company: str = "default", page: int = 1, include_contact: bool = False
    ) -> dict:
        """List normalized clients with contact details disabled by default."""
        return await superfaktura.list_clients(company, page, include_contact)

    @mcp.tool()
    @audit.audited("superfaktura_get_client")
    async def superfaktura_get_client(
        client_id: int, company: str = "default", include_contact: bool = False
    ) -> dict:
        """Read one normalized client with contact details disabled by default."""
        return await superfaktura.get_client(client_id, company, include_contact)

    @mcp.tool()
    @audit.audited("superfaktura_download_invoice_pdf")
    async def superfaktura_download_invoice_pdf(
        invoice_id: int,
        destination: str,
        language: str = "slo",
        company: str = "default",
    ) -> dict:
        """Download an invoice PDF into the workspace."""
        return await superfaktura.download_invoice_pdf(invoice_id, destination, language, company)
