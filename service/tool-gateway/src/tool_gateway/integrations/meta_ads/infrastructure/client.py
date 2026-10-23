"""Provide the read-only Meta Ads adapter."""

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, ClassVar

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.http.client import secure_http_client
from tool_gateway.infrastructure.http.limits import ResultLimiter
from tool_gateway.infrastructure.security.credentials import require_config
from tool_gateway.infrastructure.security.resources import require_allowed
from tool_gateway.infrastructure.security.urls import require_https_url


class MetaAdsClient:
    """Provide read-only operations for MetaAds."""

    def __init__(
        self,
        settings: Settings,
        limiter: ResultLimiter | None = None,
        http_client: Callable[..., Any] | None = None,
    ) -> None:
        """Initialize the client with its role-scoped configuration."""
        self.settings = settings
        self.limiter = limiter or ResultLimiter(settings)
        self.http_client = http_client

    ALLOWED_INSIGHT_FIELDS: ClassVar[set[str]] = {
        "account_id",
        "account_name",
        "ad_id",
        "ad_name",
        "adset_id",
        "adset_name",
        "campaign_id",
        "campaign_name",
        "clicks",
        "cpc",
        "cpm",
        "ctr",
        "date_start",
        "date_stop",
        "impressions",
        "reach",
        "spend",
        "actions",
        "cost_per_action_type",
        "action_values",
        "conversions",
        "conversion_values",
        "frequency",
    }
    ALLOWED_BREAKDOWNS: ClassVar[set[str]] = {
        "age",
        "gender",
        "country",
        "region",
        "publisher_platform",
        "platform_position",
        "impression_device",
        "device_platform",
    }
    ALLOWED_ACTION_BREAKDOWNS: ClassVar[set[str]] = {
        "action_type",
        "action_device",
        "action_destination",
        "action_reaction",
    }
    ALLOWED_ATTRIBUTION_WINDOWS: ClassVar[set[str]] = {
        "1d_click",
        "7d_click",
        "28d_click",
        "1d_view",
        "7d_view",
        "28d_view",
        "dda",
    }
    ALLOWED_FILTER_OPERATORS: ClassVar[set[str]] = {
        "EQUAL",
        "NOT_EQUAL",
        "IN",
        "NOT_IN",
        "GREATER_THAN",
        "LESS_THAN",
        "CONTAIN",
        "NOT_CONTAIN",
    }
    OBJECT_FIELDS: ClassVar[dict[str, set[str]]] = {
        "campaigns": {
            "id",
            "name",
            "status",
            "effective_status",
            "objective",
            "daily_budget",
            "lifetime_budget",
            "created_time",
            "updated_time",
        },
        "adsets": {
            "id",
            "name",
            "campaign_id",
            "status",
            "effective_status",
            "daily_budget",
            "lifetime_budget",
            "optimization_goal",
            "billing_event",
            "bid_strategy",
            "targeting",
            "start_time",
            "end_time",
            "created_time",
            "updated_time",
        },
        "ads": {
            "id",
            "name",
            "adset_id",
            "campaign_id",
            "status",
            "effective_status",
            "created_time",
            "updated_time",
            "creative{id,name,title,body,object_url,url_tags,thumbnail_url}",
        },
        "adcreatives": {
            "id",
            "name",
            "title",
            "body",
            "object_url",
            "url_tags",
            "thumbnail_url",
            "status",
        },
    }

    @property
    def base_url(self) -> str:
        """Return the configured base URL."""
        profile = self.settings.optional_credential("meta_ads")
        version = profile.get("graph_api_version") or self.settings.meta_graph_api_version
        return f"https://graph.facebook.com/{version}"

    @property
    def token(self) -> str:
        """Return the configured token."""
        profile = self.settings.optional_credential("meta_ads")
        return require_config(
            profile.get("access_token"),
            "Meta Ads access token",
        )

    def _account(self, account_id: str) -> str:
        """Handle internal account details."""
        return require_allowed(
            account_id, self.settings.allowed_meta_ad_account_ids, "Meta ad account"
        )

    @staticmethod
    def _date_range(since: str, until: str, max_days: int = 730) -> None:
        """Handle internal date range details."""
        start = date.fromisoformat(since)
        end = date.fromisoformat(until)
        if start > end or end > datetime.now(UTC).date() + timedelta(days=1):
            raise ValueError("Invalid Meta date range")
        if end - start > timedelta(days=max_days):
            raise ValueError(f"Meta date range cannot exceed {max_days} days")

    async def _paged(self, path: str, params: dict[str, Any]) -> dict:
        """Handle internal paged details."""
        params = {**params, "limit": 500}
        headers = {"Authorization": f"Bearer {self.token}"}
        rows: list[dict] = []
        url: str | None = f"{self.base_url}/{path.lstrip('/')}"
        async with (self.http_client or secure_http_client)(timeout=60) as client:
            while url and len(rows) < self.settings.tool_result_max_rows:
                url = require_https_url(
                    url,
                    allowed_hosts={"graph.facebook.com"},
                    label="Meta pagination URL",
                )
                response = await client.get(
                    url,
                    headers=headers,
                    params=params if not rows else None,
                )
                response.raise_for_status()
                data = response.json()
                rows.extend(data.get("data", []))
                url = data.get("paging", {}).get("next")
        return self.limiter.limit(rows)

    async def get_account(self, account_id: str) -> dict:
        """Return account."""
        account = self._account(account_id)
        params = {
            "fields": "id,name,account_status,currency,timezone_name,timezone_offset_hours_utc,amount_spent,balance",
        }
        async with (self.http_client or secure_http_client)(timeout=30) as client:
            response = await client.get(
                f"{self.base_url}/act_{account}",
                headers={"Authorization": f"Bearer {self.token}"},
                params=params,
            )
            response.raise_for_status()
            return response.json()

    async def list_objects(
        self, account_id: str, object_type: str, fields: list[str] | None = None
    ) -> dict:
        """List objects."""
        account = self._account(account_id)
        allowed = self.OBJECT_FIELDS.get(object_type)
        if not allowed:
            raise ValueError("Unsupported Meta object type")
        requested = fields or sorted(allowed)
        if not set(requested).issubset(allowed):
            raise ValueError("Unsupported Meta object fields")
        return await self._paged(f"act_{account}/{object_type}", {"fields": ",".join(requested)})

    async def activities(self, account_id: str, since: str, until: str) -> dict:
        """Handle activities."""
        account = self._account(account_id)
        self._date_range(since, until, 90)
        return await self._paged(
            f"act_{account}/activities",
            {
                "since": since,
                "until": until,
                "fields": "event_time,event_type,actor_name,object_id,object_name,extra_data",
            },
        )

    async def insights(
        self,
        account_id: str,
        since: str,
        until: str,
        level: str,
        fields: list[str],
        breakdowns: list[str] | None = None,
        action_breakdowns: list[str] | None = None,
        time_increment: str = "all_days",
        action_attribution_windows: list[str] | None = None,
        filtering: list[dict] | None = None,
    ) -> dict:
        """Handle insights."""
        account = self._account(account_id)
        self._date_range(since, until)
        if level not in {"account", "campaign", "adset", "ad"}:
            raise ValueError("Invalid insights level")
        if not fields or not set(fields).issubset(self.ALLOWED_INSIGHT_FIELDS):
            raise ValueError("Unsupported Meta insights fields")
        if not set(breakdowns or []).issubset(self.ALLOWED_BREAKDOWNS):
            raise ValueError("Unsupported Meta breakdown")
        if not set(action_breakdowns or []).issubset(self.ALLOWED_ACTION_BREAKDOWNS):
            raise ValueError("Unsupported Meta action breakdown")
        if time_increment not in {"all_days", "monthly", "1", "7", "28"}:
            raise ValueError("Unsupported Meta time_increment")
        if not set(action_attribution_windows or []).issubset(self.ALLOWED_ATTRIBUTION_WINDOWS):
            raise ValueError("Unsupported Meta attribution window")
        params: dict[str, Any] = {
            "time_range": json.dumps({"since": since, "until": until}),
            "level": level,
            "fields": ",".join(fields),
            "time_increment": time_increment,
        }
        if breakdowns:
            params["breakdowns"] = ",".join(breakdowns)
        if action_breakdowns:
            params["action_breakdowns"] = ",".join(action_breakdowns)
        if action_attribution_windows:
            params["action_attribution_windows"] = json.dumps(action_attribution_windows)
        if filtering:
            if len(filtering) > 10 or any(
                set(item) != {"field", "operator", "value"}
                or item.get("operator") not in self.ALLOWED_FILTER_OPERATORS
                or not isinstance(item.get("field"), str)
                or not str(item["field"]).startswith(("campaign.", "adset.", "ad.", "account_id"))
                for item in filtering
            ):
                raise ValueError("Invalid Meta filtering")
            params["filtering"] = json.dumps(filtering)
        return await self._paged(f"act_{account}/insights", params)
