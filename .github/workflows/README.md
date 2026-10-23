# CI and Production Deployment

## Purpose

Verify repository changes and provide manual production host/application workflows.
CI is not a live integration preflight and never provisions web-account passwords.

## Responsibilities

- CI runs workflow/script validation, docs checks, lint/type checks, test gates,
  runtime-image verification, dependency audit, and fake-transport browser tests.
- Bootstrap Production Host prepares an Ubuntu amd64/KVM host once.
- Deploy Production builds commit-addressed images, publishes GHCR, and deploys
  the selected commit over verified SSH; it has no automatic push trigger.

## Entry Points

- [CI](ci.yml)
- [Host bootstrap](bootstrap-prod-host.yml)
- [Application deployment](deploy-prod.yml)
- [Deployment script map](deploy_scripts/README.md)
- [Protected Environment inputs](environment.md)

## Dependencies and Boundaries

Use the protected GitHub Environment named `production`. Configure required reviewers
as appropriate; the [input inventory](environment.md) explains each value. Provider
OAuth remains interactive and agent-local; web accounts are created on the host.

The current ingress is HTTP-only. TLS/certificate renewal and host firewalling need
operator configuration. Expose only ingress and administration SSH; internal database,
Hermes, gateway, and frontend service ports remain private.

Runtime payloads are temporary mode-0600 files removed on runner/host. SSH host
verification is strict. Failed deployment restores the previous checkout/environment;
it does not promise schema rollback. Production initialization rejects incompatible
schema rather than enabling destructive development reset.

## Tests

`task lint` includes docs tests/checks and script syntax checks.
`task test` runs disposable/fake-based suites and synthetic Compose validation.
CI separately validates Actions/shell scripts, audits locked dependencies, verifies
the pinned Hermes image, and runs desktop/mobile Playwright projects.

Do not use working-source credentials to run local tests. Documentation CI checks
structure/targets, not semantic accuracy; fill the PR documentation checklist.

## Related Documentation

- [Configuration](../../docs/configuration.md)
- [Operations](../../docs/operations.md)
- [Host preparation](deploy_scripts/infra/README.md)
- [Application deployment](deploy_scripts/services/README.md)
- [Coding-agent and repository guidance](../../.agents/AGENTS.md)
