# Operations

## Start, Stop, and Reboot

Run lifecycle commands from the checkout, using the agents actually deployed:

```bash
task up
task agent:start AGENT=assistant
task agent:status AGENT=assistant
task agent:stop AGENT=assistant
task down
```

`task up` starts Compose, prepares runtime configuration, and waits for the backend health
route; it does not start sandbox supervisors or verify an LLM provider. `agent:start` is
supervisor-aware; `agent:stop` terminates the supervisor process group and stops the sandbox
without deleting it.
`task down` removes Compose containers/networks but does not request volume deletion.

After reboot, unlock the OS credential store if needed, verify Docker/SBX login, then
start Compose and the relevant supervisors. Do not recreate sandboxes or web accounts
merely because a service is stopped. Shut down the OS normally before removing Pi power.

## Diagnostics

```bash
task host:check
sbx ls
task runtime:verify
task deploy:validate
task code:status
docker compose --env-file .env -f infra/orchestration/docker-compose/docker-compose.yml logs --tail=100 backend
```

Treat logs as potentially sensitive; do not publish raw logs, env files, cookies, or tokens.
For unavailable agents, check sandbox/supervisor status and the configured Hermes port.
For missing tools, check manifest registration, scoped credential binding, gateway health,
and host DNS. Do not "fix" authorization by disabling allowlists or exposing listeners.
For sign-in errors, check backend health, an explicitly created account, and matching origin.
See [scripts](../scripts/README.md) and [sandbox](../infra/sandbox/README.md).

## Persistent Data and Transfer

```text
data/agents/<id>/workspace/                  user-visible files
data/agents/<id>/workspace/outputs/<date>/   generated deliverables
data/agents/<id>/hermes-state/               runtime config, OAuth, session state
data/agents/<id>/workspace-access-policy.json protected path policy
data/generated-kits/<id>/                   rendered SBX configuration
data/code/<repository>/                    mirror/current/previous/status
data/audit/<agent>.jsonl                    result-free tool audit
```

```bash
task agent:export AGENT=assistant
task agent:import AGENT=assistant ARCHIVE=data/exports/assistant-<timestamp>.tar.gz
```

Export includes the workspace, manifest, filtered Hermes state, and scoped UI/runtime
mappings; credential paths are excluded. Workspace content and chat history may still
be sensitive. Protect the archive. Import requires a missing destination, fresh web
password, source secrets, sandbox creation, and provider authorization. Missing initialized
session state fails explicitly rather than silently discarding context.

## Deployment and Database Safety

[Production workflows](../.github/workflows/README.md) are manual; deployment pulls
commit-addressed images and verifies health. Accounts/provider logins remain interactive.
Pinned runtime upgrades need separate review of Runs/Sessions/Events/Approval/Stop support.
Use [database documentation](../service/backend/src/infrastructure/database/README.md)
before initialization: incompatible non-production schemas can be destructively recreated;
production rejects incompatible schemas rather than enabling that reset.
Checkout/environment rollback does not promise database rollback. TLS, firewalling,
encrypted backups, and source-side permissions remain operator responsibilities.
