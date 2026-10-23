"""Construct Tool Gateway integration dependencies."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tool_gateway.infrastructure.configuration.settings import Settings
from tool_gateway.infrastructure.exports.paths import ExportPathResolver
from tool_gateway.infrastructure.exports.writer import TabularExporter
from tool_gateway.infrastructure.http.client import HttpClientFactory
from tool_gateway.infrastructure.http.limits import ResultLimiter
from tool_gateway.infrastructure.observability.audit import AuditRecorder
from tool_gateway.integrations.bigquery.application.service import BigQueryService
from tool_gateway.integrations.bigquery.infrastructure.client import BigQueryClient
from tool_gateway.integrations.clickup.application.service import ClickUpService
from tool_gateway.integrations.clickup.infrastructure.client import ClickUpClient
from tool_gateway.integrations.code.application.service import CodeService
from tool_gateway.integrations.code.infrastructure.client import CodeClient
from tool_gateway.integrations.google_ads.application.service import GoogleAdsService
from tool_gateway.integrations.google_ads.infrastructure.client import GoogleAdsClient
from tool_gateway.integrations.google_analytics.application.service import GoogleAnalyticsService
from tool_gateway.integrations.google_analytics.infrastructure.client import GoogleAnalyticsClient
from tool_gateway.integrations.meta_ads.application.service import MetaAdsService
from tool_gateway.integrations.meta_ads.infrastructure.client import MetaAdsClient
from tool_gateway.integrations.metabase.application.service import MetabaseService
from tool_gateway.integrations.metabase.infrastructure.client import MetabaseClient
from tool_gateway.integrations.payments.gopay.application.service import GoPayService
from tool_gateway.integrations.payments.gopay.infrastructure.client import GoPayClient
from tool_gateway.integrations.payments.stripe.application.service import StripeService
from tool_gateway.integrations.payments.stripe.infrastructure.client import StripeClient
from tool_gateway.integrations.superfaktura.application.service import SuperFakturaService
from tool_gateway.integrations.superfaktura.infrastructure.client import SuperFakturaClient


@dataclass(frozen=True)
class ApplicationContainer:
    """Hold role-scoped configuration and enabled integration services."""

    settings: Settings
    audit: AuditRecorder
    paths: ExportPathResolver
    exporter: TabularExporter
    limiter: ResultLimiter
    http: HttpClientFactory
    services: dict[str, Any]


def build_container(configuration: Settings | None = None) -> ApplicationContainer:
    """Build services only for integrations enabled by the agent manifest."""
    configuration = configuration or Settings()  # type: ignore[call-arg]
    paths = ExportPathResolver(configuration)
    exporter = TabularExporter(configuration, paths)
    limiter = ResultLimiter(configuration)
    http = HttpClientFactory()
    factories: dict[str, Callable[[], Any]] = {
        "metabase": lambda: MetabaseService(
            MetabaseClient(configuration, exporter, limiter, http.create)
        ),
        "bigquery": lambda: BigQueryService(BigQueryClient(configuration, exporter, limiter)),
        "superfaktura": lambda: SuperFakturaService(
            SuperFakturaClient(configuration, paths, exporter, limiter, http.create)
        ),
        "gopay": lambda: GoPayService(GoPayClient(configuration, limiter, http.create)),
        "stripe": lambda: StripeService(StripeClient(configuration, http.create)),
        "google_ads": lambda: GoogleAdsService(GoogleAdsClient(configuration, exporter, limiter)),
        "meta_ads": lambda: MetaAdsService(MetaAdsClient(configuration, limiter, http.create)),
        "google_analytics": lambda: GoogleAnalyticsService(
            GoogleAnalyticsClient(configuration, exporter)
        ),
        "clickup": lambda: ClickUpService(
            ClickUpClient(configuration, paths, limiter, http.create)
        ),
        "code": lambda: CodeService(CodeClient(configuration)),
    }
    enabled = {
        name: factories[name]() for name in configuration.manifest.tools if name in factories
    }
    return ApplicationContainer(
        settings=configuration,
        audit=AuditRecorder(configuration),
        paths=paths,
        exporter=exporter,
        limiter=limiter,
        http=http,
        services=enabled,
    )
