"""Test the Google Ads application service."""

from support.services import assert_service_delegates

from tool_gateway.integrations.google_ads.application.service import GoogleAdsService


def test_service_delegates_to_injected_client() -> None:
    """Expose operations from the injected Google Ads client."""
    assert_service_delegates(GoogleAdsService)
