# Production Host Preparation

## Purpose

Own one-time preparation of the standard Ubuntu amd64/KVM production host.
This is not a generic installer for every Linux distribution or Raspberry Pi.

## Responsibilities

- Establish strictly verified SSH transport.
- Install Docker, Compose, KVM support, Docker Sandboxes, and Go Task.
- Prepare operator groups without creating application accounts.

## Entry Points

- [Runner transport](bootstrap_host_via_ssh.sh)
- [Host bootstrap](remote_bootstrap_host.sh)
- [Bootstrap workflow](../../bootstrap-prod-host.yml)

## Dependencies and Boundaries

Bootstrap needs a deploy account with temporary passwordless sudo.
Open a new SSH session afterwards for docker/kvm group membership to apply.
Host changes are explicit operations, not part of ordinary lint/test commands.

Raspberry Pi images/resources/cgroups need separate verification; see the setup guide.
Never expose SSH credentials, host key payloads, or copied environment contents.

## Tests

CI validates Actions syntax and shell scripts. `task lint` checks shell syntax.
A successful static check does not prove a target host has KVM or enough resources;
operators run `task host:check` on that host separately.

## Related Documentation

- [Workflow map](../../README.md)
- [Getting started](../../../../docs/getting-started.md)
- [Application deployment](../services/README.md)
