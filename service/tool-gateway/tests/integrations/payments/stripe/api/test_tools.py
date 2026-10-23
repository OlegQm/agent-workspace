"""Test the Stripe MCP registration contract."""

from support.mcp import registered_tool_names

from tool_gateway.integrations.payments.stripe.api.tools import register_tools


def test_register_tools_exposes_stripe_operations() -> None:
    """Register the exact Stripe tool set."""
    assert registered_tool_names(register_tools) == {
        "stripe_list_objects",
        "stripe_get_object",
    }
