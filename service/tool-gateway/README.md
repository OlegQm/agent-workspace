# Tool Gateway

## Purpose

Provide manifest-scoped read-only source tools over MCP. The bundled project configuration
contains one neutral assistant and one matching gateway; additional manifests require
explicit runtime and deployment wiring. The sandbox credential proxy authenticates to the
gateway selected for that assistant.

## Responsibilities

- Register only integrations enabled by the validated agent manifest.
- Apply scope checks, bounded results/exports, and result-free audit.
- Keep source credentials outside agent workspaces.

## Entry Points

- [ASGI/MCP and console entrypoint](src/tool_gateway/entrypoints/mcp/server.py)
- [Constructor DI](src/tool_gateway/bootstrap/container.py)
- [open-agent-workspace-tool-gateway command](pyproject.toml)

## Dependencies and Boundaries

Application services depend on injected client interfaces, not API registrars.
Concrete HTTP/SDK/Git clients live in local infrastructure. Shared infrastructure
must not depend on integrations. Different integrations do not import each other;
GoPay and Stripe share only their payments namespace.
FastMCP provides MCP transport; HTTPX, SQLGlot, and source-specific SDKs implement
clients/policies. Start with `uv run --project service/tool-gateway open-agent-workspace-tool-gateway`
only after configuring the gateway identifier, matching manifest, gateway token, and source files; the
[setup guide](../../docs/getting-started.md) owns normal Compose startup.

## Tests

Run `task test` for the 100% line/branch gate. Focused pytest targets are under
`tests/bootstrap`, `tests/entrypoints`, `tests/infrastructure`, and `tests/integrations`.
Tests fake external APIs/SDKs/subprocesses; do not use live credentials.

## Related Documentation

- [Bootstrap](src/tool_gateway/bootstrap/README.md)
- [MCP entrypoint](src/tool_gateway/entrypoints/mcp/README.md)
- [configuration](src/tool_gateway/infrastructure/configuration/README.md)
- [exports](src/tool_gateway/infrastructure/exports/README.md)
- [http](src/tool_gateway/infrastructure/http/README.md)
- [observability](src/tool_gateway/infrastructure/observability/README.md)
- [security](src/tool_gateway/infrastructure/security/README.md)
- [bigquery](src/tool_gateway/integrations/bigquery/README.md)
- [clickup](src/tool_gateway/integrations/clickup/README.md)
- [code](src/tool_gateway/integrations/code/README.md)
- [google_ads](src/tool_gateway/integrations/google_ads/README.md)
- [google_analytics](src/tool_gateway/integrations/google_analytics/README.md)
- [meta_ads](src/tool_gateway/integrations/meta_ads/README.md)
- [metabase](src/tool_gateway/integrations/metabase/README.md)
- [payments](src/tool_gateway/integrations/payments/README.md)
- [superfaktura](src/tool_gateway/integrations/superfaktura/README.md)
- [Architecture](../../docs/architecture.md)
- [Coding-agent and repository guidance](../../.agents/AGENTS.md)
