"""Test the Stripe application service."""

from support.services import assert_service_delegates

from tool_gateway.integrations.payments.stripe.application.service import StripeService


def test_service_delegates_to_injected_client() -> None:
    """Expose operations from the injected Stripe client."""
    assert_service_delegates(StripeService)
