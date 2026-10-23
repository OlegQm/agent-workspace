"""Characterize Meta Ads operations without external HTTP requests."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.integrations.meta_ads.infrastructure import client as module
from tool_gateway.integrations.meta_ads.infrastructure.client import MetaAdsClient

settings = Settings()


class Response:
    """Provide one fake Graph API response."""

    def __init__(self, payload: dict) -> None:
        """Store JSON payload."""
        self.payload = payload

    def raise_for_status(self) -> None:
        """Represent success."""

    def json(self) -> dict:
        """Return JSON payload."""
        return self.payload


class Client:
    """Provide ordered fake Graph API GET responses."""

    def __init__(self, payloads: list[dict]) -> None:
        """Store payload queue."""
        self.payloads = payloads
        self.calls: list[tuple] = []

    async def __aenter__(self):
        """Enter the fake client."""
        return self

    async def __aexit__(self, *_args) -> None:
        """Exit the fake client."""

    async def get(self, url: str, **kwargs) -> Response:
        """Record GET and return the next response."""
        self.calls.append((url, kwargs))
        return Response(self.payloads.pop(0))


@pytest.fixture
def meta_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure one Meta account and token."""
    resources = SimpleNamespace(meta_ad_account_ids=["act_123"])
    monkeypatch.setattr(
        Settings,
        "manifest",
        property(lambda _self: SimpleNamespace(resources=resources)),
    )
    monkeypatch.setattr(
        Settings,
        "optional_credential",
        lambda _self, source, alias="default": (
            {"access_token": "token", "graph_api_version": "v99"} if source == "meta_ads" else {}
        ),
    )
    monkeypatch.setattr(settings, "tool_result_max_rows", 2)


def test_meta_configuration_dates_and_pagination(
    monkeypatch: pytest.MonkeyPatch,
    meta_config: None,
) -> None:
    """Characterize account configuration, date validation, and bounded pagination."""
    adapter = MetaAdsClient(settings)
    assert adapter.base_url.endswith("/v99")
    assert adapter.token == "token"
    assert adapter._account("act_123") == "123"
    with pytest.raises(ValueError, match="not allowed"):
        adapter._account("999")

    today = datetime.now(UTC).date()
    adapter._date_range(str(today - timedelta(days=2)), str(today))
    with pytest.raises(ValueError, match="Invalid"):
        adapter._date_range(str(today), str(today - timedelta(days=1)))
    with pytest.raises(ValueError, match="Invalid"):
        adapter._date_range(str(today), str(today + timedelta(days=2)))
    with pytest.raises(ValueError, match="cannot exceed"):
        adapter._date_range(str(today - timedelta(days=3)), str(today), 2)

    async def run() -> None:
        """Exercise two-page bounded collection and account retrieval."""
        client = Client(
            [
                {"data": [{"id": "1"}], "paging": {"next": "https://graph.facebook.com/n"}},
                {"data": [{"id": "2"}], "paging": {}},
                {"id": "act_123", "name": "Account"},
            ]
        )
        monkeypatch.setattr(module, "secure_http_client", lambda **_kwargs: client)
        assert (await adapter._paged("act_123/campaigns", {}))["row_count"] == 2
        assert client.calls[1][1]["params"] is None
        assert (await adapter.get_account("123"))["name"] == "Account"

    asyncio.run(run())


def test_meta_objects_activities_and_insights(
    monkeypatch: pytest.MonkeyPatch,
    meta_config: None,
) -> None:
    """Characterize object fields, activities, insights options, and validation."""
    adapter = MetaAdsClient(settings)
    calls: list[tuple[str, dict]] = []

    async def paged(path: str, params: dict) -> dict:
        """Record an adapter-level paged request."""
        calls.append((path, params))
        return {"rows": []}

    monkeypatch.setattr(adapter, "_paged", paged)
    today = datetime.now(UTC).date()
    since = str(today - timedelta(days=1))
    until = str(today)

    async def run() -> None:
        """Exercise supported operations and each invalid option."""
        await adapter.list_objects("123", "campaigns")
        await adapter.list_objects("123", "ads", ["id", "name"])
        await adapter.activities("123", since, until)
        filtering = [{"field": "campaign.id", "operator": "IN", "value": ["1"]}]
        await adapter.insights(
            "123",
            since,
            until,
            "campaign",
            ["campaign_id", "spend"],
            ["country"],
            ["action_type"],
            "7",
            ["7d_click"],
            filtering,
        )
        await adapter.insights("123", since, until, "account", ["spend"])
        with pytest.raises(ValueError, match="object type"):
            await adapter.list_objects("123", "unknown")
        with pytest.raises(ValueError, match="object fields"):
            await adapter.list_objects("123", "campaigns", ["secret"])

        invalid_cases = [
            {"level": "invalid", "fields": ["spend"]},
            {"level": "account", "fields": []},
            {"level": "account", "fields": ["secret"]},
            {"level": "account", "fields": ["spend"], "breakdowns": ["secret"]},
            {"level": "account", "fields": ["spend"], "action_breakdowns": ["secret"]},
            {"level": "account", "fields": ["spend"], "time_increment": "2"},
            {
                "level": "account",
                "fields": ["spend"],
                "action_attribution_windows": ["secret"],
            },
        ]
        for values in invalid_cases:
            with pytest.raises(ValueError):
                await adapter.insights("123", since, until, **values)

        bad_filters = [
            [{"field": "campaign.id", "operator": "BAD", "value": "1"}],
            [{"field": 1, "operator": "IN", "value": "1"}],
            [{"field": "user.email", "operator": "IN", "value": "1"}],
            [{"field": "campaign.id", "operator": "IN"}],
            [{"field": "campaign.id", "operator": "IN", "value": "1"} for _ in range(11)],
        ]
        for filtering in bad_filters:
            with pytest.raises(ValueError, match="filtering"):
                await adapter.insights(
                    "123", since, until, "account", ["spend"], filtering=filtering
                )

    asyncio.run(run())
    assert calls[0][0].endswith("campaigns")
    assert "breakdowns" in calls[3][1]
