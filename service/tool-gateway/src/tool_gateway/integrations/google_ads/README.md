# Google Ads Integration

## Purpose

Read allowed customer metadata and bounded marketing reports through GAQL.
Expose only the manifest-enabled MCP contract.

## Responsibilities

- List/get allowed customers and query SELECT-only GAQL.
- Inspect conversion actions and bounded change history.
- Export configured report results without campaign mutations.

## Entry Points

- [register_tools: names, signatures, descriptions](api/tools.py)
- [Application service](application/service.py)
- [Concrete source client](infrastructure/client.py)

## Dependencies and Boundaries

Customer scope is checked server-side. GAQL policy is local domain logic; SDK behavior
belongs to infrastructure. Change history is limited to 30 days/10,000 rows. Ads account
permissions should also be read-only.
API registrars delegate to application services; bootstrap injects client dependencies.

## Tests

`tests/integrations/google_ads` mirrors API/application/infrastructure (and domain where
present). Tests fake SDK/HTTP/Git behavior and assert success/error contracts. Gateway
bootstrap tests verify role-specific registration, schemas, and annotations.

## Related Documentation

- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
- [Credentials and scopes](../../../../../../docs/configuration.md)
