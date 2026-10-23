# Open Agent Workspace

A web workspace for configurable assistants, with isolated agent runtimes,
external tool integrations, conversation history, and workspace files. Administrators have separate
management views; permissions come from authenticated server-side accounts.

## What It Does

- Chat with an assigned agent and switch between its configured model modes.
- Search and explain permitted source data through configured read-only MCP tools.
- Upload, organize, download, and preview workspace documents, images, and text.
- Plan one Metabase chart, discover existing Questions, and explicitly send a plan
  for review when the tracker integration is configured; planning never builds a chart.
- Review user conversations and export them as JSON through authorized admin views.
- Stream run progress, handle approvals/stop, and reconnect to active runs.

## Architecture

```text
Browser -> nginx -> FastAPI -> per-agent Hermes / Docker Sandbox
                         -> PostgreSQL (accounts, UI history, run/planning state)
Sandbox -> scoped Tool Gateway -> permitted external sources
Optional Code Sync -> immutable snapshots -> gateway code tools
```

The server selects the agent from the session; the browser cannot choose a sandbox,
workspace, or Hermes session ID. PostgreSQL keeps display history while Hermes keeps
each conversation's compactable runtime context. See [architecture](docs/architecture.md).

## Requirements

The standard scripted host path is Ubuntu 24.04 amd64 with KVM, Docker Engine/Compose,
Go Task, and Docker Sandboxes `sbx >= 0.38.0`. Development checks also use Python 3.13,
uv, and Node.js 22. Agent authentication depends on the configured provider.

Current sandbox creation allocates 8 GB RAM/four CPUs per agent; reserve memory for the
web stack too. Raspberry Pi and other ARM hosts are not part of the standard scripted
host path and need independent validation. See [getting started](docs/getting-started.md).

## Quick Start: Assistant

Run from the repository root on a prepared host:

```bash
task host:check
task host:bootstrap  # only if host prerequisites are missing; requires sudo
task setup
task agent:create AGENT=assistant
task agent:auth AGENT=assistant
task user:create AGENT=assistant
task admin:create USERNAME=admin
```

The included agent manifests are safe templates: model IDs are placeholders and all
external data scopes are empty. Configure supported models before agent creation, then
add only explicitly authorized credentials and allowlists before enabling source tools.
Open `http://localhost`. Account creation prompts for a password; setup/deployment
do not create web accounts. For the default OAuth profile, complete the displayed
device-code login. API-key profiles use their configured credential instead.

External data access additionally needs scoped credentials and manifest allowlists.
The bundled assistant is the only default agent profile. Read the
[setup guide](docs/getting-started.md) before adding agents or configuring LAN access.

## Security Essentials

Never commit `.env`, passwords, tokens, OAuth state, or private data. Base64 is not encryption.
Keep source credentials in protected runtime files and grant least privilege at each source.
Public traffic goes through nginx; databases, gateways, and Hermes must stay private.

Sandbox isolation and gateway policies are not universal DLP: the current sandbox network
allows general internet access. Protected previews are not DRM. See the actual
[security boundaries](docs/security.md) before changing permissions or enabling external actions.

## Documentation

- [Documentation index and module map](docs/README.md)
- [Configuration: agents, providers, credentials, and planning review](docs/configuration.md)
- [Operations: restart, diagnostics, export/import](docs/operations.md)
- [CI and production deployment](.github/workflows/README.md)
- Service maps: [backend](service/backend/README.md), [Tool Gateway](service/tool-gateway/README.md),
  [frontend](service/frontend/README.md), [Code Sync](service/code-sync/README.md)
- [Infrastructure](infra/README.md), [configuration files](config/README.md), [scripts](scripts/README.md)

## Development and Help

```bash
npm ci --prefix service/frontend
task docs:check
task lint
task test
```

Python suites use fake external transports and disposable PostgreSQL; no working-source
credentials are required. Browser tests are described in the [frontend map](service/frontend/README.md).
For problems, start with [operations](docs/operations.md) and report only sanitized diagnostics
to the maintainers of your deployment.

Coding-agent instructions and the documentation checklist are in [`.agents/AGENTS.md`](.agents/AGENTS.md).
Tools that only auto-discover a root-level `AGENTS.md` must be configured to load this file;
the repository intentionally keeps coding-agent instructions under `.agents/`.
