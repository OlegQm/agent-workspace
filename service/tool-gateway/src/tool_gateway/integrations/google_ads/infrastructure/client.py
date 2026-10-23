"""Provide the read-only Google Ads adapter."""

from datetime import UTC, datetime, timedelta
from typing import ClassVar

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.exports.paths import ExportPathResolver
from tool_gateway.infrastructure.exports.writer import TabularExporter
from tool_gateway.infrastructure.http.limits import ResultLimiter
from tool_gateway.infrastructure.security.credentials import require_config
from tool_gateway.infrastructure.security.resources import require_allowed
from tool_gateway.integrations.google_ads.domain.policies import require_select_gaql


class GoogleAdsClient:
    """Provide read-only operations for GoogleAds."""

    def __init__(
        self,
        settings: Settings,
        exporter: TabularExporter | None = None,
        limiter: ResultLimiter | None = None,
    ) -> None:
        """Initialize the client with its role-scoped configuration."""
        self.settings = settings
        self.exporter = exporter or TabularExporter(settings, ExportPathResolver(settings))
        self.limiter = limiter or ResultLimiter(settings)

    ALLOWED_RESOURCES: ClassVar[set[str]] = {
        "ad_group",
        "ad_group_ad",
        "asset",
        "asset_group",
        "campaign",
        "campaign_asset",
        "change_event",
        "conversion_action",
        "customer",
        "geographic_view",
        "keyword_view",
        "search_term_view",
    }

    def _client(self):
        """Handle internal client details."""
        from google.ads.googleads.client import GoogleAdsClient  # type: ignore[import-untyped]

        profile = self.settings.optional_credential("google_ads")
        config = {
            "developer_token": require_config(
                profile.get("developer_token"),
                "Google Ads developer token",
            ),
            "client_id": require_config(profile.get("client_id"), "Google Ads client ID"),
            "client_secret": require_config(
                profile.get("client_secret"),
                "Google Ads client secret",
            ),
            "refresh_token": require_config(
                profile.get("refresh_token"),
                "Google Ads refresh token",
            ),
            "use_proto_plus": True,
        }
        login_customer = profile.get("login_customer_id")
        if login_customer:
            config["login_customer_id"] = str(login_customer).replace("-", "")
        return GoogleAdsClient.load_from_dict(config)

    def list_customers(self) -> dict:
        """List customers."""
        service = self._client().get_service("CustomerService")
        accessible = {
            name.rsplit("/", 1)[-1] for name in service.list_accessible_customers().resource_names
        }
        rows = [
            {"customer_id": customer_id}
            for customer_id in self.settings.allowed_google_ads_customer_ids
            if customer_id in accessible
        ]
        return self.limiter.limit(rows)

    def query(self, customer_id: str, gaql: str, destination: str | None = None) -> dict:
        """Query the requested data."""
        from google.protobuf.json_format import MessageToDict

        customer_id = require_allowed(
            customer_id, self.settings.allowed_google_ads_customer_ids, "Google Ads customer"
        )
        gaql = require_select_gaql(gaql, self.ALLOWED_RESOURCES)
        service = self._client().get_service("GoogleAdsService")
        rows = []
        row_limit = (
            self.settings.export_max_rows("google_ads")
            if destination
            else self.settings.tool_result_max_rows
        )
        for batch in service.search_stream(customer_id=customer_id, query=gaql):
            for row in batch.results:
                rows.append(MessageToDict(row._pb, preserving_proto_field_name=True))
                if len(rows) > row_limit:
                    break
            if len(rows) > row_limit:
                break
        if destination and len(rows) > row_limit:
            raise ValueError("Google Ads export exceeds TOOL_EXPORT_MAX_ROWS")
        return (
            self.exporter.write(rows, destination, "google_ads")
            if destination
            else self.limiter.limit(rows)
        )

    def get_customer(self, customer_id: str) -> dict:
        """Return customer."""
        return self.query(
            customer_id,
            "SELECT customer.id, customer.descriptive_name, customer.currency_code, "
            "customer.time_zone, customer.manager, customer.status FROM customer LIMIT 1",
        )

    def list_conversion_actions(self, customer_id: str) -> dict:
        """List conversion actions."""
        return self.query(
            customer_id,
            "SELECT conversion_action.id, conversion_action.name, conversion_action.status, "
            "conversion_action.type, conversion_action.category, "
            "conversion_action.counting_type, conversion_action.include_in_conversions_metric "
            "FROM conversion_action ORDER BY conversion_action.id LIMIT 10000",
        )

    def get_change_history(self, customer_id: str, since: str, until: str) -> dict:
        """Return change history."""
        start = datetime.fromisoformat(since)
        end = datetime.fromisoformat(until)
        start = start.replace(tzinfo=UTC) if start.tzinfo is None else start.astimezone(UTC)
        end = end.replace(tzinfo=UTC) if end.tzinfo is None else end.astimezone(UTC)
        now = datetime.now(UTC)
        if start > end or start < now - timedelta(days=30) or end > now + timedelta(minutes=5):
            raise ValueError("Google Ads change history must be within the last 30 days")
        gaql = (
            "SELECT change_event.change_date_time, change_event.change_resource_type, "
            "change_event.resource_change_operation, change_event.client_type, "
            "change_event.user_email, change_event.changed_fields, "
            "change_event.old_resource, change_event.new_resource "
            "FROM change_event "
            f"WHERE change_event.change_date_time >= '{start:%Y-%m-%d %H:%M:%S}' "
            f"AND change_event.change_date_time <= '{end:%Y-%m-%d %H:%M:%S}' "
            "ORDER BY change_event.change_date_time DESC LIMIT 10000"
        )
        return self.query(customer_id, gaql)
