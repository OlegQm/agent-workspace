"""Characterize Google Analytics SDK operations without remote requests."""

from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest
from google.analytics import admin_v1alpha, data_v1alpha, data_v1beta

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.integrations.google_analytics.infrastructure import client as module
from tool_gateway.integrations.google_analytics.infrastructure.client import (
    GoogleAnalyticsClient,
    _message,
    _validate_filter,
)

settings = Settings()


def proto(value: dict):
    """Build a minimal protobuf-like object for message serialization."""
    return SimpleNamespace(_pb=value)


class BetaClient:
    """Provide all Google Analytics Data beta API methods."""

    response = SimpleNamespace(
        dimension_headers=[SimpleNamespace(name="country")],
        metric_headers=[SimpleNamespace(name="visits")],
        rows=[
            SimpleNamespace(
                dimension_values=[SimpleNamespace(value="SK")],
                metric_values=[SimpleNamespace(value="2")],
            ),
            SimpleNamespace(
                dimension_values=[SimpleNamespace(value="CZ")],
                metric_values=[SimpleNamespace(value="3")],
            ),
        ],
        row_count=3,
        metadata=proto({"kind": "metadata"}),
        property_quota=proto({"tokens": 1}),
    )
    requests: ClassVar[list[object]] = []

    def __init__(self, credentials=None) -> None:
        """Record supplied credentials."""
        self.credentials = credentials

    def run_report(self, request):
        """Return a standard report."""
        self.requests.append(request)
        return self.response

    def run_realtime_report(self, request):
        """Return a realtime report."""
        self.requests.append(request)
        return self.response

    def get_metadata(self, *, name: str):
        """Return metadata."""
        return proto({"name": name})

    def check_compatibility(self, request):
        """Return compatibility details."""
        self.requests.append(request)
        return proto({"compatible": True})


class AlphaClient:
    """Provide the funnel report API."""

    requests: ClassVar[list[object]] = []

    def __init__(self, credentials=None) -> None:
        """Record supplied credentials."""
        self.credentials = credentials

    def run_funnel_report(self, request):
        """Return a funnel response."""
        self.requests.append(request)
        return proto({"funnel": True})


class AdminClient:
    """Provide every supported Analytics Admin method."""

    def __init__(self, credentials=None) -> None:
        """Record supplied credentials."""
        self.credentials = credentials

    def get_property(self, **kwargs):
        """Return one property."""
        return proto(kwargs)

    def list_data_streams(self, **_kwargs):
        """Return data streams."""
        return [proto({"kind": "stream"})]

    def list_big_query_links(self, **_kwargs):
        """Return BigQuery links."""
        return [proto({"kind": "bigquery"})]

    def list_custom_dimensions(self, **_kwargs):
        """Return custom dimensions."""
        return [proto({"kind": "dimension"})]

    def list_custom_metrics(self, **_kwargs):
        """Return custom metrics."""
        return [proto({"kind": "metric"})]

    def list_key_events(self, **_kwargs):
        """Return key events."""
        return [proto({"kind": "event"})]

    def list_google_ads_links(self, **_kwargs):
        """Return Ads links."""
        return [proto({"kind": "ads"})]

    def get_attribution_settings(self, **kwargs):
        """Return attribution settings."""
        return proto(kwargs)


@pytest.fixture
def analytics_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Configure one property, fake clients, serialization, and export limits."""
    resources = SimpleNamespace(google_analytics_property_ids=["123"], tool_export_limits={})
    monkeypatch.setattr(
        Settings,
        "manifest",
        property(lambda _self: SimpleNamespace(resources=resources)),
    )
    monkeypatch.setattr(settings, "agent_data_dir", tmp_path)
    monkeypatch.setattr(settings, "tool_result_max_rows", 1)
    monkeypatch.setattr(Settings, "export_max_rows", lambda _self, _source: 10)
    monkeypatch.setattr(Settings, "optional_credential", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(module, "MessageToDict", lambda value, **_kwargs: value)
    monkeypatch.setattr(data_v1beta, "BetaAnalyticsDataClient", BetaClient)
    monkeypatch.setattr(data_v1alpha, "AlphaAnalyticsDataClient", AlphaClient)
    monkeypatch.setattr(admin_v1alpha, "AnalyticsAdminServiceClient", AdminClient)


def test_message_property_rows_and_filter_validation(analytics_config: None) -> None:
    """Characterize serialization, row mapping, property scope, and filter grammar."""
    assert _message(None) == {}
    assert _message(proto({"a": 1})) == {"a": 1}
    adapter = GoogleAnalyticsClient(settings)
    assert adapter._credentials() is None
    assert adapter._property("123") == "123"
    with pytest.raises(ValueError, match="not allowed"):
        adapter._property("999")
    rows, total = adapter._rows(BetaClient.response)
    assert rows[0] == {"country": "SK", "visits": "2"}
    assert total == 3

    _validate_filter(None)
    _validate_filter({"not_expression": {"filter": {"field_name": "x", "empty_filter": {}}}})
    _validate_filter(
        {"and_group": {"expressions": [{"filter": {"field_name": "x", "string_filter": {}}}]}}
    )
    _validate_filter(
        {"or_group": {"expressions": [{"filter": {"field_name": "x", "numeric_filter": {}}}]}}
    )
    invalid = [
        ({"filter": {}}, 6, "nesting"),
        ({}, 0, "expression"),
        ({"unknown": {}}, 0, "expression"),
        ({"and_group": {"expressions": []}}, 0, "group"),
        ({"or_group": {"expressions": [{} for _ in range(21)]}}, 0, "group"),
        ({"filter": {"string_filter": {}}}, 0, "field_name"),
        ({"filter": {"field_name": "x"}}, 0, "exactly one"),
        (
            {"filter": {"field_name": "x", "string_filter": {}, "empty_filter": {}}},
            0,
            "exactly one",
        ),
    ]
    for value, depth, message in invalid:
        with pytest.raises(ValueError, match=message):
            _validate_filter(value, depth)


def test_standard_realtime_metadata_and_compatibility_reports(
    analytics_config: None,
) -> None:
    """Characterize report requests, output modes, and compatibility calls."""
    adapter = GoogleAnalyticsClient(settings)
    report = adapter.run_report(
        "123",
        "2026-01-01",
        "2026-01-31",
        ["country"],
        ["visits"],
        limit=0,
        dimension_filter={"filter": {"field_name": "country", "empty_filter": {}}},
        metric_filter={"filter": {"field_name": "visits", "numeric_filter": {}}},
        order_bys=[{"desc": True}],
        offset=-1,
    )
    assert report["rows"] == [{"country": "SK", "visits": "2"}]
    assert report["truncated"] is True
    assert report["metadata"] == {"kind": "metadata"}
    exported = adapter.run_report(
        "123",
        date_ranges=[{"start_date": "2026-01-01", "end_date": "2026-01-31"}],
        destination="outputs/analytics.json",
    )
    assert exported["row_count"] == 2
    realtime = adapter.run_realtime_report("123", ["country"], ["visits"], limit=0)
    assert realtime["row_count"] == 3
    assert adapter.get_metadata("123")["name"].endswith("/metadata")
    assert adapter.check_compatibility("123", [], []) == {"compatible": True}
    assert adapter.check_compatibility(
        "123",
        ["country"],
        ["visits"],
        {"filter": {"field_name": "country", "empty_filter": {}}},
        {"filter": {"field_name": "visits", "empty_filter": {}}},
    ) == {"compatible": True}

    invalid_ranges = [
        [{"start_date": None, "end_date": None}],
        [{"start_date": "x", "end_date": "y"} for _ in range(5)],
    ]
    for ranges in invalid_ranges:
        with pytest.raises(ValueError, match="date ranges"):
            adapter.run_report("123", date_ranges=ranges)


def test_funnel_and_admin_reports(analytics_config: None) -> None:
    """Characterize funnel options and every supported Admin resource."""
    adapter = GoogleAnalyticsClient(settings)
    steps = [
        {"name": "Visit", "event_name": "page_view"},
        {"name": "Buy", "event_name": "purchase"},
    ]
    assert adapter.run_funnel_report(
        "123", "2026-01-01", "2026-01-31", steps, True, "country", "eventName", 0
    ) == {"funnel": True}
    assert adapter.run_funnel_report("123", "2026-01-01", "2026-01-31", steps) == {"funnel": True}
    for invalid_steps in ([steps[0]], steps * 6):
        with pytest.raises(ValueError, match="between 2 and 10"):
            adapter.run_funnel_report("123", "a", "b", invalid_steps)
    with pytest.raises(ValueError, match="only name"):
        adapter.run_funnel_report(
            "123", "a", "b", [{"name": "a", "event_name": "a"}, {"name": "b"}]
        )

    resources = [
        "property",
        "data_streams",
        "bigquery_links",
        "custom_dimensions",
        "custom_metrics",
        "key_events",
        "google_ads_links",
        "attribution_settings",
    ]
    for resource in resources:
        result = adapter.admin_metadata("123", resource)
        if resource in {"property", "attribution_settings"}:
            assert isinstance(result, dict)
        else:
            assert result["row_count"] == 1
    with pytest.raises(ValueError, match="Unsupported"):
        adapter.admin_metadata("123", "unknown")


def test_role_scoped_oauth_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Build OAuth credentials from the role-scoped profile."""
    monkeypatch.setattr(
        type(settings),
        "optional_credential",
        lambda self, source, alias="default": (
            {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "refresh_token": "refresh-token",
            }
            if source == "google_analytics"
            else {}
        ),
    )
    credentials = GoogleAnalyticsClient(settings)._credentials()
    assert credentials.client_id == "client-id"
    assert credentials.refresh_token == "refresh-token"
