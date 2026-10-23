# Backend Shared Infrastructure

## Purpose

Own technical facilities used across backend features: settings and database access.
Feature-specific Hermes, filesystem, and tracker adapters remain inside their features.

## Responsibilities

- Validate origins, environment, limits, and fail-closed planning integration settings.
- Provide the async database engine/session factory and canonical ORM state.
- Separate settings validation from account/agent business rules.

## Entry Points

- [Environment settings](settings.py)
- [Database ownership](database/README.md)

## Dependencies and Boundaries

Shared infrastructure does not import features. Settings load environment/.env, so tests
must use explicit fake values and avoid loading a working credential file. Enabled review
features require complete validated configuration; disabled defaults do not grant access.

## Tests

`tests/infrastructure/test_settings.py` covers configuration and validation.
The database subtree has its own mirrored tests. The full lint gate checks architecture
contracts in addition to Ruff and docstrings.

## Related Documentation

- [Configuration](../../../../docs/configuration.md)
- [Backend map](../../README.md)
- [Architecture](../../../../docs/architecture.md)
