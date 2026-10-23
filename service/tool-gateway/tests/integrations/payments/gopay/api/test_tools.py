"""Test the GoPay MCP registration contract."""

from support.mcp import registered_tool_names

from tool_gateway.integrations.payments.gopay.api.tools import register_tools


def test_register_tools_exposes_gopay_operations() -> None:
    """Register the exact GoPay tool set."""
    assert registered_tool_names(register_tools) == {
        "gopay_get_payment",
        "gopay_get_payments",
    }
