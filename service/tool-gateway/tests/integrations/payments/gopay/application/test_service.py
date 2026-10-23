"""Test the GoPay application service."""

from support.services import assert_service_delegates

from tool_gateway.integrations.payments.gopay.application.service import GoPayService


def test_service_delegates_to_injected_client() -> None:
    """Expose operations from the injected GoPay client."""
    assert_service_delegates(GoPayService)
