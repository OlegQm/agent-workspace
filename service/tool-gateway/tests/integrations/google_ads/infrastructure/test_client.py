"""Characterize Google Ads SDK operations without remote requests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.ads.googleads.client import GoogleAdsClient as GoogleAdsSdkClient
from google.protobuf.struct_pb2 import Struct

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.integrations.google_ads.infrastructure.client import GoogleAdsClient

settings = Settings()


class AdsService:
    """Provide accessible customers and streamed query batches."""

    def __init__(self, rows: list[dict]) -> None:
        """Convert dictionaries to protobuf-backed result rows."""
        self.rows = []
        for value in rows:
            message = Struct()
            message.update(value)
            self.rows.append(SimpleNamespace(_pb=message))
        self.calls: list[tuple[str, str]] = []

    def list_accessible_customers(self):
        """Return accessible customer resource names."""
        return SimpleNamespace(resource_names=["customers/123", "customers/999"])

    def search_stream(self, customer_id: str, query: str):
        """Return two batches to characterize bounded streaming."""
        self.calls.append((customer_id, query))
        midpoint = max(1, len(self.rows) // 2)
        return [
            SimpleNamespace(results=self.rows[:midpoint]),
            SimpleNamespace(results=self.rows[midpoint:]),
        ]


class Client:
    """Return fake Google Ads services."""

    def __init__(self, service: AdsService) -> None:
        """Store a shared service."""
        self.service = service

    def get_service(self, _name: str) -> AdsService:
        """Return the configured service."""
        return self.service


@pytest.fixture
def ads_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Configure one Google Ads customer and bounded exports."""
    resources = SimpleNamespace(google_ads_customer_ids=["123"], tool_export_limits={})
    monkeypatch.setattr(
        Settings,
        "manifest",
        property(lambda _self: SimpleNamespace(resources=resources)),
    )
    monkeypatch.setattr(settings, "agent_data_dir", tmp_path)
    monkeypatch.setattr(settings, "tool_result_max_rows", 1)
    monkeypatch.setattr(Settings, "export_max_rows", lambda _self, _source: 2)


def test_google_ads_client_and_customers(
    monkeypatch: pytest.MonkeyPatch,
    ads_config: None,
) -> None:
    """Characterize OAuth configuration and accessible-customer intersection."""
    profile = {
        "developer_token": "developer",
        "client_id": "client",
        "client_secret": "secret",
        "refresh_token": "refresh",
        "login_customer_id": "111-222",
    }
    monkeypatch.setattr(
        Settings,
        "optional_credential",
        lambda _self, source, alias="default": profile if source == "google_ads" else {},
    )
    captured: dict = {}

    def load(config: dict):
        """Capture SDK configuration."""
        captured.update(config)
        return "client"

    monkeypatch.setattr(GoogleAdsSdkClient, "load_from_dict", load)
    assert GoogleAdsClient(settings)._client() == "client"
    assert captured["login_customer_id"] == "111222"

    profile.pop("login_customer_id")
    GoogleAdsClient(settings)._client()
    assert captured["use_proto_plus"] is True

    service = AdsService([])
    adapter = GoogleAdsClient(settings)
    monkeypatch.setattr(adapter, "_client", lambda: Client(service))
    assert adapter.list_customers() == {
        "rows": [{"customer_id": "123"}],
        "row_count": 1,
        "truncated": False,
    }


def test_google_ads_queries_and_delegates(
    monkeypatch: pytest.MonkeyPatch,
    ads_config: None,
) -> None:
    """Characterize bounded streaming, export limits, and helper queries."""
    service = AdsService([{"id": 1}, {"id": 2}, {"id": 3}])
    adapter = GoogleAdsClient(settings)
    monkeypatch.setattr(adapter, "_client", lambda: Client(service))
    gaql = "SELECT campaign.id FROM campaign"
    assert adapter.query("123", gaql)["truncated"] is True
    with pytest.raises(ValueError, match="MAX_ROWS"):
        adapter.query("123", gaql, "outputs/too-many.json")

    service.rows.pop()
    exported = adapter.query("123", gaql, "outputs/ads.json")
    assert exported["row_count"] == 2

    calls: list[tuple[str, str]] = []

    def query(customer_id: str, value: str, destination=None) -> dict:
        """Capture delegated GAQL."""
        calls.append((customer_id, value))
        return {"destination": destination}

    monkeypatch.setattr(adapter, "query", query)
    adapter.get_customer("123")
    adapter.list_conversion_actions("123")
    assert "FROM customer" in calls[0][1]
    assert "FROM conversion_action" in calls[1][1]


def test_google_ads_change_history_ranges(
    monkeypatch: pytest.MonkeyPatch,
    ads_config: None,
) -> None:
    """Characterize naive/aware timestamps and each rejected date range."""
    adapter = GoogleAdsClient(settings)
    captured: list[str] = []
    monkeypatch.setattr(
        adapter,
        "query",
        lambda _customer, gaql: captured.append(gaql) or {"rows": []},
    )
    now = datetime.now(UTC)
    adapter.get_change_history(
        "123",
        (now - timedelta(hours=1)).replace(tzinfo=None).isoformat(),
        now.replace(tzinfo=None).isoformat(),
    )
    adapter.get_change_history(
        "123",
        (now - timedelta(hours=2)).astimezone(UTC).isoformat(),
        (now - timedelta(hours=1)).astimezone(UTC).isoformat(),
    )
    assert "FROM change_event" in captured[0]

    invalid = [
        (now, now - timedelta(seconds=1)),
        (now - timedelta(days=31), now),
        (now, now + timedelta(minutes=6)),
    ]
    for start, end in invalid:
        with pytest.raises(ValueError, match="last 30 days"):
            adapter.get_change_history("123", start.isoformat(), end.isoformat())
