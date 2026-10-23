# Infrastructure

## Purpose

Describe host-facing runtime assembly, separate from application feature code.
This directory does not own users, source permissions, or business calculations.

## Responsibilities

- Compose application services and private listeners.
- Configure nginx, Hermes images/kits, and host orchestration.
- Keep runtime secrets and working state outside versioned infrastructure.

## Entry Points

- [Service orchestration](orchestration/README.md)
- [HTTP/TLS ingress](nginx/README.md)
- [Docker Sandbox runtime](sandbox/README.md)

## Dependencies and Boundaries

Compose services and Docker Sandboxes have different lifecycles. The standard scripted
host is Ubuntu amd64; other distributions and ARM hosts require separate verification.
Do not mistake private gateway mounts for strict per-agent service isolation.

## Tests

Run `task deploy:validate` for synthetic Compose validation and `task lint` for script
syntax checks. Runtime image verification builds a local image separately; it does
not authorize a live agent or test external sources.

## Related Documentation

- [Platform and setup guide](../docs/getting-started.md)
- [Security](../docs/security.md)
- [Deployment](../.github/workflows/README.md)
