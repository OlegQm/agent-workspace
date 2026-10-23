# BigQuery Integration

## Purpose

Read allowlisted dataset/table/partition metadata and bounded query results.
Expose only the manifest-enabled MCP contract.

## Responsibilities

- List/get datasets and tables and inspect partition metadata.
- Dry-run queries and enforce dataset/billed-byte policy.
- Return bounded results or CSV/JSON exports.

## Entry Points

- [register_tools: names, signatures, descriptions](api/tools.py)
- [Application service](application/service.py)
- [Concrete source client](infrastructure/client.py)

## Dependencies and Boundaries

Use parsed SELECT/WITH-only queries and explicit dataset scope. Billing limits and source
IAM both matter. The client uses the Google SDK and shared exporter/limiter; no dataset
creation, ingestion, or schema mutation tool is registered.
API registrars delegate to application services; bootstrap injects client dependencies.

## Tests

`tests/integrations/bigquery` mirrors API/application/infrastructure (and domain where
present). Tests fake SDK/HTTP/Git behavior and assert success/error contracts. Gateway
bootstrap tests verify role-specific registration, schemas, and annotations.

## Related Documentation

- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
- [Credentials and scopes](../../../../../../docs/configuration.md)
