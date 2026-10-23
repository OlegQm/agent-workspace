"""Test the code application service."""

from support.services import assert_service_delegates

from tool_gateway.integrations.code.application.service import CodeService


def test_service_delegates_to_injected_client() -> None:
    """Expose operations from the injected code client."""
    assert_service_delegates(CodeService)
