# Code Sync

## Purpose

Fetch explicitly configured repositories into read-only snapshots for gateway code tools.
The default repository inventory is empty; no upstream is contacted until configured.
Do not grant a sandbox the Git credential or a mutable upstream checkout.

## Responsibilities

- Enforce configured repository/branch ownership and fetch-only Git operations.
- Treat an empty inventory as a successful no-op.
- Restrict aliases to filesystem-safe names.
- Publish `current` atomically after a successful checkout and retain `previous`.
- Record safe status and keep the last good snapshot on failure.

## Entry Points

- [daemon / once / status entrypoint](src/code_sync/main.py)
- [Non-argument Git authentication](git-askpass.sh)
- [Optional repository inventory](../../config/repositories.yaml)

## Dependencies and Boundaries

Only this service receives the read token. Gateway clients consume immutable snapshots.
Aliases must be added to both the repository inventory and the assistant manifest allowlist.
The implementation depends on Git and PyYAML. Its console command is
`uv run --project service/code-sync open-agent-workspace-code-sync daemon`; repository configuration,
data directories, and the token file must be configured before a real synchronization.
The default daemon refresh interval is five minutes; with an empty inventory it performs
no network access. `task code:sync` performs one sync
and `task code:status` reads status. Do not embed credentials in repository URLs.

## Tests

Run `uv run --project service/code-sync --extra dev pytest service/code-sync/tests`.
`test_sync.py` exercises Git/filesystem/error behavior with isolated fixtures and fakes.
Never use a real token for tests.

## Related Documentation

- [Code MCP tools](../tool-gateway/src/tool_gateway/integrations/code/README.md)
- [Operations](../../docs/operations.md)
- [Architecture](../../docs/architecture.md)
- [Coding-agent and repository guidance](../../.agents/AGENTS.md)
