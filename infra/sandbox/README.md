# Docker Sandbox Runtime

## Purpose

Build the pinned Hermes shell-agent image and render each agent's kit/configuration.
Docker Sandboxes own isolation and runtime lifecycle.

## Responsibilities

- Start Hermes under the workspace-local external supervisor.
- Bind per-agent gateway credentials at the host proxy.
- Keep OAuth/runtime state separate from user-visible files.

## Entry Points

- [Pinned Hermes image](Dockerfile)
- [Hermes launcher](start-hermes.sh)
- [Profile/tool configuration](hermes-config.template.yaml)
- [Credential injection and network policy](kit/spec.template.yaml)

## Dependencies and Boundaries

The kit gives TOOL_GATEWAY_TOKEN a proxy-managed sentinel; Hermes sends that header and
the proxy replaces it for the agent-tools loopback alias only. The current allow policy
includes general internet access; this is not DLP. No upstream runtime patches are used.
The shell image avoids the standalone s6 lifecycle so SBX controls execution.

## Tests

Renderer/backend configuration tests validate profiles/templates with fake inputs.
`task runtime:verify` builds/probes standard endpoints with synthetic auth, no provider
login. ARM images/resource constraints require separate host verification.

## Related Documentation

- [Host requirements](../../docs/getting-started.md)
- [Provider setup](../../docs/configuration.md)
- [Supervisor/keyring recovery](../../docs/operations.md)
