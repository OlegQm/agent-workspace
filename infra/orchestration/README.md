# Compose Orchestration

## Purpose

Assemble web/backend/gateways/code-sync/PostgreSQL with private runtime mounts.
Agent Docker Sandboxes are not created by Compose.

## Responsibilities

- Define local service images/build contexts, networking, health, and data mounts.
- Overlay commit-addressed production images without duplicating the service model.
- Scope credential files and privileges per host service.

## Entry Points

- [Base Compose](docker-compose/docker-compose.yml)
- [Production image overlay](docker-compose/docker-compose.prod.yml)
- [TOOL_GATEWAY_DNS selection](../../scripts/resolve_host_dns.sh)

## Dependencies and Boundaries

Multiple -f files merge in order; the production file overrides image fields. Public
access is through nginx; database, gateways, and Hermes stay private. Review data/agents
mounts independently of sandbox isolation. DNS may need the host's working resolver.

## Tests

`task deploy:validate` uses synthetic secrets to validate the merged model without
production access. Gateway configuration tests cover DNS wiring. No Compose up/down
is part of documentation checks.

## Related Documentation

- [Infrastructure](../README.md)
- [Mount/network boundaries](../../docs/security.md)
- [Deployment](../../.github/workflows/deploy_scripts/services/README.md)
