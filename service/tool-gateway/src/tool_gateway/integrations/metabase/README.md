# Metabase Integration

## Purpose

Discover, explain, run, and export existing Questions within the role's scope.
Expose only the manifest-enabled MCP contract.

## Responsibilities

- Search Questions/dashboards and inspect definitions/collection items.
- Read allowed database/table/field metadata and safe settings/permissions/subscriptions.
- Run existing Questions, export results, or execute permitted read-only SQL.

## Entry Points

- [register_tools: names, signatures, descriptions](api/tools.py)
- [Application service](application/service.py)
- [Concrete source client](infrastructure/client.py)

## Dependencies and Boundaries

Question/collection/database ownership must be checked, including dashboard references.
Local domain policies preserve parsed PostgreSQL read-only semantics. The planner reuses
these tools but never creates a Question. No direct source-database tunnel is needed.
API registrars delegate to application services; bootstrap injects client dependencies.

## Tests

`tests/integrations/metabase` mirrors API/application/infrastructure (and domain where
present). Tests fake SDK/HTTP/Git behavior and assert success/error contracts. Gateway
bootstrap tests verify role-specific registration, schemas, and annotations.

## Related Documentation

- [Planning consumer](../../../../../backend/src/features/metabase_planning/README.md)
- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
- [Credentials and scopes](../../../../../../docs/configuration.md)
