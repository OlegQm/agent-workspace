"""Test the SuperFaktura MCP registration contract."""

from support.mcp import registered_tool_names

from tool_gateway.integrations.superfaktura.api.tools import register_tools


def test_register_tools_exposes_superfaktura_operations() -> None:
    """Register the exact SuperFaktura tool set."""
    assert registered_tool_names(register_tools) == {
        "superfaktura_list_companies",
        "superfaktura_list_invoices",
        "superfaktura_get_invoice",
        "superfaktura_get_invoice_payments",
        "superfaktura_list_clients",
        "superfaktura_get_client",
        "superfaktura_download_invoice_pdf",
    }
