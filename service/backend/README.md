# Backend

## Purpose

Own the authenticated HTTP application and its persistent user-visible state.
Assistant and administrator views share this service but not authorization.

## Responsibilities

- Compose FastAPI through an injected application container.
- Own agents, identity, chat, workspace, and Metabase-planning features.
- Persist history and workflow state; adapt Hermes without patching its internals.

## Entry Points

- [HTTP app factory and console entrypoint](src/bootstrap/app.py)
- [Account/history/database CLI](src/entrypoints/cli/admin.py)
- [Console commands and dependencies](pyproject.toml)

## Dependencies and Boundaries

Use `bootstrap`, `entrypoints`, shared `infrastructure`, and feature-local layers.
`open-agent-workspace-ai-backend` starts the server; `open-agent-workspace-ai-admin` exposes operator commands.
The service uses FastAPI/Uvicorn, Pydantic, and SQLAlchemy/asyncpg with PostgreSQL.
The development entrypoint is `uv run --project service/backend open-agent-workspace-ai-backend`;
normal multi-service startup belongs to the [setup guide](../../docs/getting-started.md).
Settings must be configured before importing the application. Do not run the real CLI
against working data in tests. Provider and gateway credentials are separate.

## Tests

Run `task test` for the backend's 100% line/branch gate, or focused pytest modules
through `uv run --project service/backend --extra dev pytest ...`.
Tests mirror `src`; disposable PostgreSQL fixtures live in `tests/support`.

## Related Documentation

- [Bootstrap](src/bootstrap/README.md)
- [Administrative CLI](src/entrypoints/cli/README.md)
- [Shared infrastructure](src/infrastructure/README.md)
- [agents](src/features/agents/README.md)
- [identity](src/features/identity/README.md)
- [chat](src/features/chat/README.md)
- [workspace](src/features/workspace/README.md)
- [metabase_planning](src/features/metabase_planning/README.md)
- [Architecture](../../docs/architecture.md)
- [Coding-agent and repository guidance](../../.agents/AGENTS.md)
