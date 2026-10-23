# Gateway Security Primitives

## Purpose

Provide shared technical checks for URLs, SQL, resource scope, and credentials.
Keep these technical facilities independent of specific integrations.

## Responsibilities

- Validate allowed remote destinations and credential availability.
- Reject unsupported/mutating SQL structures under existing policy.
- Enforce explicit manifest resource membership.

## Entry Points

- [URL checks](urls.py)
- [SQL checks](sql.py)
- [Resource checks](resources.py)
- [Credential checks](credentials.py)

## Dependencies and Boundaries

Dialect-specific Metabase/PostgreSQL and Google Ads rules belong near integrations.
These checks do not replace source-side least privilege or guarantee arbitrary SQL is
harmless. Security hardening is a separate behavior change, not a documentation refactor.

## Tests

`tests/infrastructure/security` characterizes declared restrictions and error branches.
Use synthetic SQL/URLs/policies; never probe a working database or loosen grants.

## Related Documentation

- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
