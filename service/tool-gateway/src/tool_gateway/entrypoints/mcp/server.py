"""Expose the Tool Gateway MCP and ASGI entrypoints."""

import uvicorn

from tool_gateway.bootstrap.application import build_application
from tool_gateway.bootstrap.container import build_container
from tool_gateway.entrypoints.mcp.middleware import BearerAuthMiddleware

container = build_container()
settings = container.settings
mcp = build_application(container)
app = BearerAuthMiddleware(
    mcp.streamable_http_app(), settings.token, settings.gateway_max_request_body_bytes
)


def main() -> None:
    """Run the command-line entry point."""
    uvicorn.run(
        app,
        host=settings.gateway_host,
        port=settings.gateway_port,
        proxy_headers=False,
        server_header=False,
    )
