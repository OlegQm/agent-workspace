# Architecture

## Service Flow

```text
Browser -> nginx -> FastAPI -> selected agent's Hermes / Docker Sandbox
                         -> PostgreSQL (accounts, UI history, run and planning state)
Sandbox -> scoped Tool Gateway -> allowed external sources
Optional Code Sync -> immutable snapshots -> Tool Gateway code tools
```

Agent identity is derived from the authenticated server session. The browser does not
choose a sandbox, workspace, tool policy, or Hermes session ID. Regular accounts belong
to one configured agent; administrators have separate management views.

## Ownership and Layers

[Backend features](../service/backend/README.md) group agents, identity, chat, workspace,
and Metabase planning. [Tool Gateway integrations](../service/tool-gateway/README.md)
group source-specific tools. Both Python services separate composition (`bootstrap`),
entrypoints, shared infrastructure, and feature/integration ownership.

Within a feature/integration, `api` owns transport contracts, `application` coordinates
use cases, `domain` holds rules without network/persistence I/O, and `infrastructure`
implements external adapters. Empty layers are omitted. Stateful dependencies use
constructor-injected classes; pure mappings and endpoint operations may be functions.
Import-linter enforces the boundaries; tests mirror production ownership.

[Frontend](../service/frontend/README.md) composes ordinary chat, planning, files, tools,
and read-only admin conversation views through one authenticated workspace composable.
Its shape is documented as it exists, not as a new frontend architecture.

## State and Lifecycle

PostgreSQL stores users, hashed login sessions, full display messages/events, agent runs,
conversation runtime mappings, and planning/review state. A draft chat stays browser-local
until its first run is created atomically. One partial unique index permits only one
active run per agent. Ordinary run events stream through SSE with reconnect/recovery.

Each persisted conversation has a private random Hermes session ID. Later turns load
the runtime transcript from Hermes. Native in-place compaction may shorten that transcript;
PostgreSQL remains the UI history. Missing initialized runtime state fails explicitly.

Planning conversations are marked in ordinary history. Structured, validated results
drive persisted planning buttons/state, not assistant wording. The planner chooses when
to repeat read-only discovery. Review submission is a separate explicit user action.

## Files and Processes

Agent workspaces and Hermes state live under separate per-agent directories. A sandbox
supervisor prevents shell-agent hibernation and restarts the Hermes command. Compose does
not create or start sandboxes by itself. Shared host services have different boundaries
from the sandbox; mounts and source allowlists must be reviewed independently.

[Code Sync](../service/code-sync/README.md) is an optional source-code integration. With
configured repositories it publishes `current`/`previous` snapshots and retains the last
good snapshot after failures. An empty inventory is a successful no-op; gateways read
snapshots, not the Git token.
See [security](security.md) for actual guarantees and [operations](operations.md) for storage.
