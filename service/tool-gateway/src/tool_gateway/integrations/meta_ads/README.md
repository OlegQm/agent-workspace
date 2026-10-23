# Meta Ads Integration

## Purpose

Read permitted ad accounts, objects, activity, and Insights.
Expose only the manifest-enabled MCP contract.

## Responsibilities

- Fetch safe account/campaign/ad-set/ad/creative fields.
- Bound activity date ranges and Insights dimensions.
- Validate breakdowns and attribution windows.

## Entry Points

- [register_tools: names, signatures, descriptions](api/tools.py)
- [Application service](application/service.py)
- [Concrete source client](infrastructure/client.py)

## Dependencies and Boundaries

Fixed fields and account allowlists prevent arbitrary Graph API access. HTTP client
errors/redirects must retain credential boundaries. No ad creation, editing, or deletion
is part of the registered tools.
API registrars delegate to application services; bootstrap injects client dependencies.

## Tests

`tests/integrations/meta_ads` mirrors API/application/infrastructure (and domain where
present). Tests fake SDK/HTTP/Git behavior and assert success/error contracts. Gateway
bootstrap tests verify role-specific registration, schemas, and annotations.

## Related Documentation

- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
- [Credentials and scopes](../../../../../../docs/configuration.md)
