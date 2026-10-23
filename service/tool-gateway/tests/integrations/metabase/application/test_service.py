"""Test the Metabase application service."""

from support.services import assert_service_delegates

from tool_gateway.integrations.metabase.application.service import MetabaseService


def test_service_delegates_to_injected_client() -> None:
    """Expose operations from the injected Metabase client."""
    assert_service_delegates(MetabaseService)
