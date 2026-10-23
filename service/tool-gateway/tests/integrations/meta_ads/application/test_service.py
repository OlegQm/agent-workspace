"""Test the Meta Ads application service."""

from support.services import assert_service_delegates

from tool_gateway.integrations.meta_ads.application.service import MetaAdsService


def test_service_delegates_to_injected_client() -> None:
    """Expose operations from the injected Meta Ads client."""
    assert_service_delegates(MetaAdsService)
