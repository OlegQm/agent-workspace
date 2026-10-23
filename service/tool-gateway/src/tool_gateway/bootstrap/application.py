"""Compose the role-scoped MCP application."""

from collections.abc import Callable
from typing import Any

from mcp.server.transport_security import TransportSecuritySettings

from tool_gateway.bootstrap.container import ApplicationContainer
from tool_gateway.entrypoints.mcp.annotations import ReadOnlyFastMCP
from tool_gateway.integrations.bigquery.api.tools import register_tools as register_bigquery
from tool_gateway.integrations.clickup.api.tools import register_tools as register_clickup
from tool_gateway.integrations.code.api.tools import register_tools as register_code
from tool_gateway.integrations.google_ads.api.tools import register_tools as register_google_ads
from tool_gateway.integrations.google_analytics.api.tools import (
    register_tools as register_google_analytics,
)
from tool_gateway.integrations.meta_ads.api.tools import register_tools as register_meta_ads
from tool_gateway.integrations.metabase.api.tools import register_tools as register_metabase
from tool_gateway.integrations.payments.gopay.api.tools import register_tools as register_gopay
from tool_gateway.integrations.payments.stripe.api.tools import register_tools as register_stripe
from tool_gateway.integrations.superfaktura.api.tools import (
    register_tools as register_superfaktura,
)


def build_application(container: ApplicationContainer) -> ReadOnlyFastMCP:
    """Validate configuration and register the enabled MCP integrations."""
    settings = container.settings
    manifest = settings.manifest
    if manifest.id != settings.gateway_role or manifest.resources.environment != "prod":
        raise RuntimeError("Gateway role does not match a PROD agent manifest")
    mcp = ReadOnlyFastMCP(
        f"Open Agent Workspace {settings.gateway_role.title()} Data",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[
                f"{settings.gateway_role}-tools.127.0.0.1.sslip.io:{settings.gateway_port}",
                f"127.0.0.1:{settings.gateway_port}",
                f"localhost:{settings.gateway_port}",
            ]
        ),
    )
    registrars: dict[str, Callable[[Any, Any], None]] = {
        "metabase": register_metabase,
        "bigquery": register_bigquery,
        "superfaktura": register_superfaktura,
        "gopay": register_gopay,
        "stripe": register_stripe,
        "google_ads": register_google_ads,
        "meta_ads": register_meta_ads,
        "google_analytics": register_google_analytics,
        "clickup": register_clickup,
        "code": register_code,
    }
    for name in manifest.tools:
        service = container.services.get(name)
        registrar = registrars.get(name)
        if service is not None and registrar is not None:
            registrar(mcp, service, container.audit)
    return mcp
