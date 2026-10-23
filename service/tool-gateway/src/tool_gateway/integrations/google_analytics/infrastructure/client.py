"""Provide the read-only Google Analytics adapter."""

from typing import Any

from google.protobuf.json_format import MessageToDict

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.exports.paths import ExportPathResolver
from tool_gateway.infrastructure.exports.writer import TabularExporter
from tool_gateway.infrastructure.security.credentials import require_config
from tool_gateway.infrastructure.security.resources import require_allowed
from tool_gateway.infrastructure.security.urls import require_https_url


def _message(value: Any) -> dict:
    """Handle internal message details."""
    if value is None:
        return {}
    return MessageToDict(value._pb, preserving_proto_field_name=True)


def _validate_filter(value: dict | None, depth: int = 0) -> None:
    """Validate filter."""
    if value is None:
        return
    if depth > 5:
        raise ValueError("Google Analytics filter nesting is too deep")
    allowed = {"and_group", "or_group", "not_expression", "filter"}
    if len(value) != 1 or not set(value).issubset(allowed):
        raise ValueError("Invalid Google Analytics filter expression")
    if "not_expression" in value:
        _validate_filter(value["not_expression"], depth + 1)
    for key in ("and_group", "or_group"):
        if key in value:
            expressions = value[key].get("expressions", [])
            if not expressions or len(expressions) > 20:
                raise ValueError("Invalid Google Analytics filter group")
            for expression in expressions:
                _validate_filter(expression, depth + 1)
    if "filter" in value:
        item = value["filter"]
        if not item.get("field_name"):
            raise ValueError("Google Analytics filter field_name is required")
        modes = {
            "string_filter",
            "in_list_filter",
            "numeric_filter",
            "between_filter",
            "empty_filter",
        }
        if len(set(item) & modes) != 1:
            raise ValueError("Google Analytics filter requires exactly one filter type")


class GoogleAnalyticsClient:
    """Provide read-only operations for GoogleAnalytics."""

    def __init__(
        self,
        settings: Settings,
        exporter: TabularExporter | None = None,
    ) -> None:
        """Initialize the client with its role-scoped configuration."""
        self.settings = settings
        self.exporter = exporter or TabularExporter(settings, ExportPathResolver(settings))

    def _credentials(self) -> Any:
        """Handle internal credentials details."""
        profile = self.settings.optional_credential("google_analytics")
        if not profile:
            return None
        from google.oauth2.credentials import Credentials

        return Credentials(
            token=None,
            refresh_token=require_config(
                profile.get("refresh_token"), "Google Analytics refresh token"
            ),
            token_uri=require_https_url(
                str(profile.get("token_uri") or "https://oauth2.googleapis.com/token"),
                allowed_hosts={"oauth2.googleapis.com"},
                label="Google OAuth token URL",
            ),
            client_id=require_config(profile.get("client_id"), "Google Analytics client ID"),
            client_secret=require_config(
                profile.get("client_secret"), "Google Analytics client secret"
            ),
        )

    def _property(self, property_id: str) -> str:
        """Handle internal property details."""
        return require_allowed(
            property_id,
            self.settings.manifest.resources.google_analytics_property_ids,
            "Google Analytics property",
        )

    @staticmethod
    def _rows(response: Any) -> tuple[list[dict], int]:
        """Handle internal rows details."""
        headers = [header.name for header in response.dimension_headers] + [
            header.name for header in response.metric_headers
        ]
        rows = []
        for row in response.rows:
            values = [value.value for value in row.dimension_values] + [
                value.value for value in row.metric_values
            ]
            rows.append(dict(zip(headers, values, strict=True)))
        return rows, response.row_count

    def run_report(
        self,
        property_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        dimensions: list[str] | None = None,
        metrics: list[str] | None = None,
        limit: int = 10_000,
        date_ranges: list[dict] | None = None,
        dimension_filter: dict | None = None,
        metric_filter: dict | None = None,
        order_bys: list[dict] | None = None,
        offset: int = 0,
        destination: str | None = None,
    ) -> dict:
        """Run report."""
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            FilterExpression,
            Metric,
            OrderBy,
            RunReportRequest,
        )

        property_id = self._property(property_id)
        ranges = date_ranges or [{"start_date": start_date, "end_date": end_date}]
        if not 1 <= len(ranges) <= 4 or any(
            not r.get("start_date") or not r.get("end_date") for r in ranges
        ):
            raise ValueError("One to four complete date ranges are required")
        _validate_filter(dimension_filter)
        _validate_filter(metric_filter)
        request = RunReportRequest(
            property=f"properties/{property_id}",
            date_ranges=[DateRange(**item) for item in ranges],
            dimensions=[Dimension(name=name) for name in dimensions or []],
            metrics=[Metric(name=name) for name in metrics or []],
            dimension_filter=FilterExpression(**dimension_filter) if dimension_filter else None,
            metric_filter=FilterExpression(**metric_filter) if metric_filter else None,
            order_bys=[OrderBy(**item) for item in order_bys or []],
            offset=max(offset, 0),
            limit=min(max(limit, 1), self.settings.export_max_rows("google_analytics")),
            return_property_quota=True,
        )
        response = BetaAnalyticsDataClient(credentials=self._credentials()).run_report(request)
        rows, total = self._rows(response)
        if destination:
            result = self.exporter.write(rows, destination, "google_analytics")
        else:
            result = {
                "rows": rows[: self.settings.tool_result_max_rows],
                "row_count": total,
                "truncated": total > min(len(rows), self.settings.tool_result_max_rows),
            }
        result["metadata"] = _message(response.metadata)
        result["property_quota"] = _message(response.property_quota)
        return result

    def run_realtime_report(
        self, property_id: str, dimensions: list[str], metrics: list[str], limit: int = 10_000
    ) -> dict:
        """Run realtime report."""
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import Dimension, Metric, RunRealtimeReportRequest

        property_id = self._property(property_id)
        response = BetaAnalyticsDataClient(credentials=self._credentials()).run_realtime_report(
            RunRealtimeReportRequest(
                property=f"properties/{property_id}",
                dimensions=[Dimension(name=name) for name in dimensions],
                metrics=[Metric(name=name) for name in metrics],
                limit=min(max(limit, 1), self.settings.tool_result_max_rows),
                return_property_quota=True,
            )
        )
        rows, total = self._rows(response)
        return {
            "rows": rows,
            "row_count": total,
            "property_quota": _message(response.property_quota),
        }

    def get_metadata(self, property_id: str) -> dict:
        """Return metadata."""
        from google.analytics.data_v1beta import BetaAnalyticsDataClient

        property_id = self._property(property_id)
        response = BetaAnalyticsDataClient(credentials=self._credentials()).get_metadata(
            name=f"properties/{property_id}/metadata"
        )
        return _message(response)

    def check_compatibility(
        self,
        property_id: str,
        dimensions: list[str],
        metrics: list[str],
        dimension_filter: dict | None = None,
        metric_filter: dict | None = None,
    ) -> dict:
        """Check compatibility."""
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            CheckCompatibilityRequest,
            Dimension,
            FilterExpression,
            Metric,
        )

        property_id = self._property(property_id)
        _validate_filter(dimension_filter)
        _validate_filter(metric_filter)
        response = BetaAnalyticsDataClient(credentials=self._credentials()).check_compatibility(
            CheckCompatibilityRequest(
                property=f"properties/{property_id}",
                dimensions=[Dimension(name=name) for name in dimensions],
                metrics=[Metric(name=name) for name in metrics],
                dimension_filter=(
                    FilterExpression(**dimension_filter) if dimension_filter else None
                ),
                metric_filter=FilterExpression(**metric_filter) if metric_filter else None,
            )
        )
        return _message(response)

    def run_funnel_report(
        self,
        property_id: str,
        start_date: str,
        end_date: str,
        steps: list[dict],
        open_funnel: bool = False,
        breakdown_dimension: str | None = None,
        next_action_dimension: str | None = None,
        limit: int = 10_000,
    ) -> dict:
        """Run funnel report."""
        from google.analytics.data_v1alpha import AlphaAnalyticsDataClient
        from google.analytics.data_v1alpha.types import (
            DateRange,
            Dimension,
            Funnel,
            FunnelBreakdown,
            FunnelEventFilter,
            FunnelFilterExpression,
            FunnelNextAction,
            FunnelStep,
            RunFunnelReportRequest,
        )

        property_id = self._property(property_id)
        if not 2 <= len(steps) <= 10:
            raise ValueError("A funnel requires between 2 and 10 steps")
        funnel_steps = []
        for step in steps:
            if set(step) != {"name", "event_name"}:
                raise ValueError("Each funnel step requires only name and event_name")
            funnel_steps.append(
                FunnelStep(
                    name=step["name"],
                    filter_expression=FunnelFilterExpression(
                        funnel_event_filter=FunnelEventFilter(event_name=step["event_name"])
                    ),
                )
            )
        request = RunFunnelReportRequest(
            property=f"properties/{property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            funnel=Funnel(is_open_funnel=open_funnel, steps=funnel_steps),
            limit=min(max(limit, 1), self.settings.tool_result_max_rows),
            return_property_quota=True,
        )
        if breakdown_dimension:
            request.funnel_breakdown = FunnelBreakdown(
                breakdown_dimension=Dimension(name=breakdown_dimension)
            )
        if next_action_dimension:
            request.funnel_next_action = FunnelNextAction(
                next_action_dimension=Dimension(name=next_action_dimension)
            )
        response = AlphaAnalyticsDataClient(credentials=self._credentials()).run_funnel_report(
            request
        )
        return _message(response)

    def admin_metadata(self, property_id: str, resource: str) -> dict:
        """Handle admin metadata."""
        from google.analytics.admin_v1alpha import AnalyticsAdminServiceClient

        property_id = self._property(property_id)
        client = AnalyticsAdminServiceClient(credentials=self._credentials())
        parent = f"properties/{property_id}"
        methods = {
            "property": lambda: client.get_property(name=parent),
            "data_streams": lambda: list(client.list_data_streams(parent=parent)),
            "bigquery_links": lambda: list(client.list_big_query_links(parent=parent)),
            "custom_dimensions": lambda: list(client.list_custom_dimensions(parent=parent)),
            "custom_metrics": lambda: list(client.list_custom_metrics(parent=parent)),
            "key_events": lambda: list(client.list_key_events(parent=parent)),
            "google_ads_links": lambda: list(client.list_google_ads_links(parent=parent)),
            "attribution_settings": lambda: client.get_attribution_settings(
                name=f"{parent}/attributionSettings"
            ),
        }
        if resource not in methods:
            raise ValueError("Unsupported Google Analytics Admin resource")
        value = methods[resource]()
        if isinstance(value, list):
            return {"rows": [_message(item) for item in value], "row_count": len(value)}
        return _message(value)
