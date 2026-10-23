# Deployment Environment Inputs

This is the workflow input inventory, not a source of secret values. Never copy
credential values into examples, issues, logs, or versioned files.

## GitHub Environment

Create a protected `production` environment and require approval when deployment
needs explicit authorization. Add only the environment secrets needed by the
chosen deployment target.

### Remote host

- `DEPLOY_SSH_HOST`: server IP or SSH hostname.
- `DEPLOY_SSH_USER`: dedicated non-root deploy account.
- `DEPLOY_SSH_PORT`: SSH port; normally `22`.
- `DEPLOY_SSH_PRIVATE_KEY` or `DEPLOY_SSH_PRIVATE_KEY_B64`: private half of a
  dedicated deployment key whose public half is in the account's
  `authorized_keys`.
- `DEPLOY_SSH_KNOWN_HOSTS`: verified host-key line. Verify the fingerprint
  through a trusted hosting console before storing it.
- `REMOTE_APP_DIR`: dedicated persistent checkout, for example
  `$HOME/open-agent-workspace-ai-workspace`.
- `DEPLOY_GHCR_USERNAME`: optional registry username; the workflow actor is
  used by default.
- `DEPLOY_GITHUB_TOKEN`: optional short-lived token used only by the remote
  deployment process to fetch repository content and private images.

### Application and database

- `APP_BASE_URL`: application origin, such as `http://<server-address>` before
  a domain and TLS are configured.
- `APP_SECRET_KEY`: stable random application secret, generated locally.
- `POSTGRES_DB` and `POSTGRES_USER`: application database name and role.
- `POSTGRES_PASSWORD`: stable random password; rotate it with the database
  procedure rather than changing it on an existing volume.
- `HERMES_API_KEY_ASSISTANT` and `TOOL_GATEWAY_TOKEN_ASSISTANT`: independent
  random values for the bundled assistant.

### External read-only integrations

- `ASSISTANT_SOURCES_YAML_B64`
- `GOOGLE_SERVICE_ACCOUNT_JSON_B64`
- `CODE_SYNC_GITHUB_TOKEN_B64`

Populate only values for explicitly enabled integrations. Keep them in the
deployment secret store and never print decoded values in a terminal.
`CODE_SYNC_GITHUB_TOKEN_B64` becomes the internal runtime value
`GITHUB_READ_TOKEN_B64`. The current runtime-secret bundle requires a non-empty value,
although it is unused while the default repository inventory is empty. When GitHub
upstreams are configured, use a read-only token scoped to those repositories.

### Optional planning navigation and review

- `METABASE_PLANNING_METABASE_LINKS_ENABLED`: false unless links are preflighted.
- `METABASE_PUBLIC_URL`: configured HTTPS Metabase origin.
- `METABASE_PLANNING_YOUTRACK_ENABLED`: false unless review writes are preflighted.
- `YOUTRACK_BASE_URL`: configured HTTPS tracker origin.
- `YOUTRACK_TOKEN`: secret scoped to required project/actions.
- `YOUTRACK_PROJECT_ID`: resolved target project identifier.
- `YOUTRACK_ASSIGNEE_ID`: resolved tracker user identifier.
- `YOUTRACK_ASSIGNEE_FIELD_ID`: resolved user-assignment custom-field identifier.

Enabled actions require complete coherent values; partial configuration fails
closed. Read [configuration](../../docs/configuration.md) before enabling
external actions. See [workflow ownership](README.md) and
[deployment procedures](deploy_scripts/services/README.md).
