# MCP Entrypoint

## Purpose

Expose the stateless streamable HTTP MCP application with bearer authentication.
Keep HTTP transport restrictions separate from integration business policy.

## Responsibilities

- Export runtime `mcp`, ASGI `app`, and console `main`.
- Check authorization and body size including streamed bytes.
- Apply read-only tool annotations and configured host validation.

## Entry Points

- [open-agent-workspace-tool-gateway](server.py)
- [BearerAuthMiddleware](middleware.py)
- [ReadOnlyFastMCP](annotations.py)

## Dependencies and Boundaries

Allow only the configured gateway host/port and aliases. Headers/tokens are never tool
arguments. A transport error does not authorize a fallback request. Gateway listeners
remain private; the sandbox proxy supplies the real credential at the host boundary.

## Tests

`tests/entrypoints/mcp` covers startup, authorization, streamed limits, HTTP errors,
registration annotations, and server invocation. Requests use synthetic tokens/fake apps;
no source API call is needed.

## Related Documentation

- [Composition](../../bootstrap/README.md)
- [Credential proxy](../../../../../../infra/sandbox/README.md)
- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
