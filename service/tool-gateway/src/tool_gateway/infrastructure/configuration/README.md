# Gateway Configuration

## Purpose

Validate selected agent manifests, secret-file inputs, resource scope, and result limits.
Keep these technical facilities independent of specific integrations.

## Responsibilities

- Load the selected agent manifest and runtime source credential shape.
- Require gateway token strength for the configured environment.
- Resolve per-source limits and opt-in source settings.

## Entry Points

- [Settings](settings.py)
- [Manifest/source models](models.py)

## Dependencies and Boundaries

Configuration must match a PROD-scoped manifest. Credentials are read from protected
runtime mounts; empty allowlists deny access. The bundled assistant has empty source scopes.
Do not copy secret values into docs or tool schemas. Settings are shared; provider-specific
request behavior belongs to integrations.

## Tests

`tests/infrastructure/configuration` covers model/settings validation and Compose DNS.
Renderer tests under `tests/entrypoints/scripts` exercise synthetic secret files.

## Related Documentation

- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
