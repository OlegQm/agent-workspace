# Workspace Scripts

## Purpose

Expose operator lifecycle commands and repository verification without duplicating
application business logic. Read the command's effects before invoking it.

## Responsibilities

- Prepare agent profiles/kits and scoped runtime credential files.
- Manage sandbox supervisors, accounts, agent transfer, and source snapshots.
- Run lint, tests, documentation checks, and synthetic deployment validation.

## Entry Points

- [Task/Make command dispatcher](workspace.sh)
- [Documentation checker](check_docs.mjs) and [fixture tests](tests/check_docs.test.mjs)
- [Validated profile renderer](render_agent_hermes_config.py)
- [Credential capture/render/prune](render_runtime_secrets.py)
- [Gateway DNS selection](resolve_host_dns.sh)
- [Backend startup readiness check](wait_for_backend.py) and [tests](tests/wait_for_backend.test.mjs)
- [Local pinned-runtime verification](verify_hermes_runtime.sh)

## Dependencies and Boundaries

`task` is the primary command surface; Make provides aliases. Lifecycle commands can
write local runtime data, create accounts, or contact providers. Verification must not
implicitly run setup, auth, sync, or deployment. Import/render tools must not print secrets.

## Tests

Documentation and backend-readiness helper tests use Node's test runner and temporary local
fixtures. Existing renderer tests live beside their backend CLI/gateway script owners. Run
`task lint`, `task test`, and `task deploy:validate` with fake/disposable resources.
`task docs:check` (or `make docs-check`) runs fixtures and the repository check using
the frontend's installed Markdown-It. Git ignores and runtime/cache directories are
excluded. Only local file/image targets are checked, not anchors or external URLs.

## Related Documentation

- [Operator procedures](../docs/operations.md)
- [Configuration](../docs/configuration.md)
- [Verification and documentation policy](../.agents/AGENTS.md)
