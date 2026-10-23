# Google Analytics Integration

## Purpose

Read allowed properties through report, realtime, metadata, and Admin APIs.
Expose only the manifest-enabled MCP contract.

## Responsibilities

- Run bounded reports/exports, realtime, and supported alpha funnel reports.
- Check metadata and metric/dimension compatibility.
- Read configured Admin get/list resources.

## Entry Points

- [register_tools: names, signatures, descriptions](api/tools.py)
- [Application service](application/service.py)
- [Concrete source client](infrastructure/client.py)

## Dependencies and Boundaries

Properties must be explicitly allowlisted; default manifests select the permitted PROD
properties. Google SDK calls are isolated in the client. Metadata access is not permission
to modify tracking configuration, users, or property settings.
API registrars delegate to application services; bootstrap injects client dependencies.

## Tests

`tests/integrations/google_analytics` mirrors API/application/infrastructure (and domain where
present). Tests fake SDK/HTTP/Git behavior and assert success/error contracts. Gateway
bootstrap tests verify role-specific registration, schemas, and annotations.

## Related Documentation

- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
- [Credentials and scopes](../../../../../../docs/configuration.md)
