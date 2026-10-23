# Deployment Scripts

## Purpose

Separate runner-side SSH transport from host-side infrastructure/application work.
These scripts implement the manual workflows, not everyday development commands.

## Responsibilities

- Prepare host prerequisites in the infrastructure area.
- Deploy exact application revisions and protected runtime configuration in services.
- Keep credentials out of logs/arguments and clean temporary payloads.

## Entry Points

- [Infrastructure scripts](infra/README.md)
- [Application scripts](services/README.md)

## Dependencies and Boundaries

`*_via_ssh.sh` runs on the Actions runner and enforces verified SSH host keys.
`remote_*.sh` runs on the host. Temporary credential payloads use mode 0600.
Deployment initializes the application database but does not create web accounts.

Provider OAuth and account passwords remain interactive operator tasks.
A checkout/environment rollback is not database rollback.

## Tests

CI runs shellcheck/actionlint and shell syntax checks. Renderer tests use synthetic
payloads; `task deploy:validate` checks merged Compose without a production connection.
Do not invoke remote scripts as a documentation test.

## Related Documentation

- [Workflow map](../README.md)
- [Environment inventory](../environment.md)
- [Operations](../../../docs/operations.md)
