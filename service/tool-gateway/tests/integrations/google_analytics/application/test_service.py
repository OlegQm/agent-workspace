"""Test the Google Analytics application service."""

from support.services import assert_service_delegates

from tool_gateway.integrations.google_analytics.application.service import GoogleAnalyticsService


def test_service_delegates_to_injected_client() -> None:
    """Expose operations from the injected Google Analytics client."""
    assert_service_delegates(GoogleAnalyticsService)
