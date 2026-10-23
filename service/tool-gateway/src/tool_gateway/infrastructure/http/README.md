# Gateway HTTP

## Purpose

Provide common credential-bearing HTTP clients and bounded result shaping.
Keep these technical facilities independent of specific integrations.

## Responsibilities

- Disable ambient proxy trust and automatic redirects by default.
- Centralize client construction for dependency injection.
- Apply result limits before returning/exporting integration data.

## Entry Points

- [HttpClientFactory](client.py)
- [ResultLimiter](limits.py)

## Dependencies and Boundaries

Source-specific clients validate their allowed remote hosts and redirect cases.
Shared infrastructure does not know integration ownership. Never allow caller-provided
URLs to bypass resource/credential scope or return raw sensitive response bodies.

## Tests

`tests/infrastructure/http` checks client construction and limit behavior without real
requests. Each integration's mirrored client tests cover provider errors/redirects.

## Related Documentation

- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
