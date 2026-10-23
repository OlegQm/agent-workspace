# Production Application Deployment

## Purpose

Deploy an exact application revision without replacing agent workspaces or OAuth state.
Accounts and agent authorization are explicit post-deployment operations.

## Responsibilities

- Validate protected Environment inputs and transfer temporary runtime payloads.
- Pull immutable images, prepare runtime files, initialize database state, and check health.
- Restore previous checkout/environment on failure and remove credential payloads.

## Entry Points

- [Input renderer](create_runtime_env.py)
- [Runner SSH deployment](deploy_prod_via_ssh.sh)
- [Host deployment](remote_deploy_prod.sh)
- [Synthetic configuration validator](validate_deployment_config.sh)

## Dependencies and Boundaries

Host prerequisites must already be prepared. The production image overlay replaces
image names in the base Compose model. Persistent state stays on host mounts/volumes.
Database initialization can fail for incompatible production schemas; deployment
does not promise an automatic data/schema rollback. Never use dev reset on working data.

After first deployment, operators explicitly create/authorize the bundled assistant:
`task agent:create AGENT=assistant`, `task agent:auth AGENT=assistant`,
`task user:create AGENT=assistant`, and `task admin:create USERNAME=admin`.
Passwords are prompted,
never GitHub Secrets. Keep OAuth, workspace, and database backups separately protected.

## Tests

`task deploy:validate` uses synthetic credentials and validates the merged model,
including host DNS selection, without production access. Renderer tests and CI
shellcheck cover failure paths; do not run a live deploy merely to verify docs.

## Related Documentation

- [Workflow map](../../README.md)
- [Environment inventory](../../environment.md)
- [Operations](../../../../docs/operations.md)
- [Database initialization](../../../../service/backend/src/infrastructure/database/README.md)
