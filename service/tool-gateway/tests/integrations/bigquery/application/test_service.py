"""Test the BigQuery application service."""

from support.services import assert_service_delegates

from tool_gateway.integrations.bigquery.application.service import BigQueryService


def test_service_delegates_to_injected_client() -> None:
    """Expose operations from the injected BigQuery client."""
    assert_service_delegates(BigQueryService)
