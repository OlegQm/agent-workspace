# Stripe Integration

## Purpose

Read allowed payment-provider objects for configured accounts.
Expose only the manifest-enabled MCP contract.

## Responsibilities

- List supported object types with bounded filters.
- Fetch one supported object by ID.
- Reject arbitrary resource types and unsupported query fields.

## Entry Points

- [register_tools: names, signatures, descriptions](api/tools.py)
- [Application service](application/service.py)
- [Concrete source client](infrastructure/client.py)

## Dependencies and Boundaries

The client uses scoped keys and fixed HTTP paths. No object creation, refunds, or account
administration is exposed. Do not treat a broad provider key as authorization to add
mutating tools; preserve manifest and field restrictions.
API registrars delegate to application services; bootstrap injects client dependencies.

## Tests

`tests/integrations/payments/stripe` mirrors API/application/infrastructure (and domain where
present). Tests fake SDK/HTTP/Git behavior and assert success/error contracts. Gateway
bootstrap tests verify role-specific registration, schemas, and annotations.

## Related Documentation

- [Gateway map](../../../../../README.md)
- [Security](../../../../../../../docs/security.md)
- [Credentials and scopes](../../../../../../../docs/configuration.md)
