# nginx Ingress

## Purpose

Serve the web app and proxy authenticated backend traffic on the host-facing origin.
Internal service listeners are not intended to be public.

## Responsibilities

- Route static assets/API/SSE and bound request/connection behavior.
- Apply CSP and other browser security headers.
- Replace untrusted forwarded headers and provide a TLS configuration template.

## Entry Points

- [Current HTTP ingress](nginx.conf)
- [TLS template](nginx.tls.conf.template)
- [Frontend static server](../../service/frontend/nginx.conf)

## Dependencies and Boundaries

APP_BASE_URL and secure-cookie settings must match the exposed origin. A template is
not installed TLS: certificate issuance/renewal and firewalling are operator tasks.
Keep PostgreSQL, Hermes, and gateway ports off public interfaces.

## Tests

Deployment validation checks Compose wiring; backend HTTP/composition and frontend E2E
cover application contracts. Static configuration review must accompany any ingress
header, rate, origin, or streaming change.

## Related Documentation

- [Service wiring](../orchestration/README.md)
- [HTTP security](../../docs/security.md)
- [Production operations](../../docs/operations.md)
