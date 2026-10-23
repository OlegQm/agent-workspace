# SuperFaktura Integration

## Purpose

Read financial invoices/credit notes, payment fields, clients, and invoice PDFs.
Expose only the manifest-enabled MCP contract.

## Responsibilities

- List allowlisted companies with safe display names.
- Normalize invoices and payment fields; export bounded results.
- Provide opt-in client contacts and controlled PDF downloads.

## Entry Points

- [register_tools: names, signatures, descriptions](api/tools.py)
- [Application service](application/service.py)
- [Concrete source client](infrastructure/client.py)

## Dependencies and Boundaries

An integration is available only when selected by the agent manifest and its required
credentials and company allowlist are configured. Raw embedded client/company snapshots
are not exposed. Company IDs, contact opt-ins, query paths, and download limits are
validated; no invoice creation/editing/deletion is registered.
API registrars delegate to application services; bootstrap injects client dependencies.

## Tests

`tests/integrations/superfaktura` mirrors API/application/infrastructure (and domain where
present). Tests fake SDK/HTTP/Git behavior and assert success/error contracts. Gateway
bootstrap tests verify manifest-selected registration, schemas, and annotations.

## Related Documentation

- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
- [Credentials and scopes](../../../../../../docs/configuration.md)
