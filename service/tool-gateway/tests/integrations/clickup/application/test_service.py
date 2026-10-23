"""Test the ClickUp application service."""

from support.services import assert_service_delegates

from tool_gateway.integrations.clickup.application.service import ClickUpService


def test_service_delegates_to_injected_client() -> None:
    """Expose operations from the injected ClickUp client."""
    assert_service_delegates(ClickUpService)
