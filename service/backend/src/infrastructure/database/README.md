# Backend Database

## Purpose

Own ORM mappings, async sessions, and startup initialization.
This PostgreSQL instance stores application state, not data from connected source systems.

## Responsibilities

- Keep mappings in models.py and engine/session construction in session.py.
- Coordinate canonical schema creation, existing compatibility operations, and cleanup.
- Reject incompatible production schemas; allow explicit coordinator-controlled dev reset.

## Entry Points

- [ORM mappings](models.py)
- [Async session factory](session.py)
- [DatabaseInitializer](initialization.py)
- [Existing compatibility operations](migrations/schema.py)
- [Empty-conversation cleanup](migrations/data.py)

## Dependencies and Boundaries

Initialization detects missing mapped columns after existing compatibility work. In a
non-production app container, an incompatible schema may be dropped/recreated; production
fails instead. This is not a general migration framework or rollback guarantee.
Transactions, unique constraints, and caller scoping remain necessary.

## Tests

`tests/infrastructure/database` uses a disposable PostgreSQL 17 container.
Session fixtures create/drop only test tables. Coverage includes initialization errors,
reset paths, compatibility operations, relationships, and run uniqueness.

## Related Documentation

- [Operational safety](../../../../../docs/operations.md)
- [Shared infrastructure](../README.md)
- [Backend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
