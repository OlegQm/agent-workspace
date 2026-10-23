# Workspace Feature

## Purpose

Own scoped file operations, previews, protected-path policy, and admin history views.
Regular users operate only within their assigned agent workspace.

## Responsibilities

- Resolve safe paths and expose file metadata/uploads/downloads/mutations.
- Translate pure policy/domain errors at the API boundary.
- Provide admin read-only conversations/JSON export and protected-path management.

## Entry Points

- [Regular workspace endpoints](api/user_router.py)
- [Admin files/history/export](api/admin_router.py)
- [Policy use cases](application/policies/operations.py)
- [Pure path rules](domain/policies/paths.py)

## Dependencies and Boundaries

Protected originals can be previewable while ordinary copy/download/mutation is denied.
Admins may manage files and policies but cannot invoke agent turns. File policies apply
independently of source tool allowlists and sandbox network settings.

## Tests

`tests/features/workspace` mirrors API, policies, filesystem, previews, and confidentiality.
Composition tests cover end-to-end role/protection behavior; frontend E2E tests verify
preview/export controls and responsive layouts without external source data.

## Related Documentation

- [Document previews](infrastructure/previews/README.md)
- [Restricted-content guard](infrastructure/confidentiality/README.md)
- [Security limitations](../../../../../docs/security.md)
- [Backend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
