# Getting Started

## Prerequisites

The standard scripted host path targets Ubuntu 24.04 amd64 with usable KVM,
Docker Engine/Compose, Go Task, and Docker Sandboxes `sbx >= 0.38.0`.
Local development checks also need Python 3.13, uv, Node.js 22, and npm.
See the [scripts](../scripts/README.md) and [sandbox](../infra/sandbox/README.md).

The current creation command allocates 8 GB and four CPUs per sandbox.
Reserve additional memory for the web stack and for every extra agent sandbox. These are
script defaults, not manifest-configurable resource limits.
Provider authentication must match the configured profile. The default profile uses
a Codex account; API-key profiles use their selected provider instead.

## First Assistant

Run from the repository root on a prepared host:

```bash
task host:check
task host:bootstrap  # only when prerequisites are missing; requires sudo
task setup
task agent:create AGENT=assistant
task agent:auth AGENT=assistant
task user:create AGENT=assistant
task admin:create USERNAME=admin
```

Before `agent:create`, replace the example model IDs in the assistant manifest with supported
provider IDs. Source allowlists intentionally start empty; configure only approved
scopes and credentials before enabling external data tools.
After bootstrap, open a new shell so group memberships take effect. Do not run
bootstrap on an already configured host just to restart the application.
The web stack opens at `http://localhost`. Configure `APP_BASE_URL` for another origin.
`task setup` and `task up` wait up to 60 seconds for the local backend health check before
reporting startup complete. The check uses loopback only and does not validate an LLM
provider.
Account commands prompt for a password without echoing it; setup/deployment do not
create web accounts. Administrator privileges come from `is_admin`, not the username.

For the default OAuth profile, complete the displayed Hermes device-code flow in a
browser. It needs no localhost callback. Approve the sandbox credential binding only
for the expected agent gateway endpoint. Keep secrets in ignored local configuration.

## Source Access and Additional Agents

The [configuration guide](configuration.md) explains source credentials and allowlists.
A running web stack or a stored credential alone does not grant access to external data.
Configure only the intended sources and scopes before enabling integrations.

The bundled assistant is the only default profile. Additional agents can use the same
lifecycle commands with a matching manifest, prompts, gateway/deployment wiring, credentials,
and explicit scopes; a YAML file alone does not create or authorize an agent.

## Raspberry Pi and Other Linux Hosts

The maintained scripted host path targets Ubuntu amd64. Raspberry Pi and other ARM/Linux
hosts may require compatible container images, KVM, memory cgroups, storage, and sandbox
authentication; no turnkey ARM deployment is promised. Validate these prerequisites
independently before using the application on such a host.

For LAN access, route browser traffic through nginx and keep Hermes, gateways, and
PostgreSQL private. Host naming, firewalling, and client isolation depend on the local
network. See [operations](operations.md) for service lifecycle and diagnostics.
