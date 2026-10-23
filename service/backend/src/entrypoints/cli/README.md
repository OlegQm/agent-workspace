# Administrative CLI

## Purpose

Expose explicit operator actions for accounts, initialization, and history transfer.
The CLI is not a browser endpoint and is not automatically run by documentation checks.

## Responsibilities

- Create regular/admin accounts with explicit persisted role flags.
- Initialize application tables through the database coordinator.
- Export/import scoped history without transferring web passwords.

## Entry Points

- [open-agent-workspace-ai-admin](admin.py)
- [Task wrappers for CLI actions](../../../../../scripts/workspace.sh)

## Dependencies and Boundaries

Commands require configured database/agent paths. Interactive account creation prompts
without echoing passwords; usernames do not imply privileges. A history archive and
runtime state can contain sensitive business context even when OAuth is excluded.

## Tests

`tests/entrypoints/cli/test_admin.py` covers command paths and account/history behavior.
Profile-renderer tests also live under CLI ownership. Use isolated database/session fakes
or disposable PostgreSQL; do not initialize a working database.

## Related Documentation

- [Database initialization](../../infrastructure/database/README.md)
- [History transfer](../../../../../docs/operations.md)
- [Backend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
