"""Test the SuperFaktura application service."""

from support.services import assert_service_delegates

from tool_gateway.integrations.superfaktura.application.service import SuperFakturaService


def test_service_delegates_to_injected_client() -> None:
    """Expose operations from the injected SuperFaktura client."""
    assert_service_delegates(SuperFakturaService)
