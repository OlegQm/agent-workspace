# GoPay Integration

## Purpose

Read the status/details of payments in explicitly allowed accounts.
Expose only the manifest-enabled MCP contract.

## Responsibilities

- Resolve configured account credentials.
- Fetch one payment or a bounded list of payment IDs.
- Return normalized provider results without mutation tools.

## Entry Points

- [register_tools: names, signatures, descriptions](api/tools.py)
- [Application service](application/service.py)
- [Concrete source client](infrastructure/client.py)

## Dependencies and Boundaries

The client may authenticate to obtain a provider token; that is not a business payment
write. No payment creation, cancellation, capture, or refund is exposed. Account allowlists
and read-only source credentials remain essential.
API registrars delegate to application services; bootstrap injects client dependencies.

## Tests

`tests/integrations/payments/gopay` mirrors API/application/infrastructure (and domain where
present). Tests fake SDK/HTTP/Git behavior and assert success/error contracts. Gateway
bootstrap tests verify role-specific registration, schemas, and annotations.

## Related Documentation

- [Gateway map](../../../../../README.md)
- [Security](../../../../../../../docs/security.md)
- [Credentials and scopes](../../../../../../../docs/configuration.md)
