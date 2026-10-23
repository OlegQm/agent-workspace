# File Browser and Previews

## Purpose

Expose safe workspace file actions and read-only format previews.
Keep controls consistent with established responsive workspace behavior.

## Responsibilities

- Support upload/drop/paste, folders, download, rename, delete, and relative-path copying.
- Preview DOCX/XLSX/PDF, images, and text.
- Respect protected-item action restrictions and bounded/virtualized rendering.

## Entry Points

- [FilePanel](FilePanel.vue)
- [DocumentPreviewDialog](DocumentPreviewDialog.vue)
- [DOCX blocks](DocxParagraph.vue)
- [Permission-aware actions](FileEntryActions.vue)

## Dependencies and Boundaries

Backend path/policy checks remain authoritative. Preview visibility is not download
permission and browser restrictions are not DRM. Never bypass the API with an arbitrary
filesystem path or expose cached private preview locations.

## Tests

Workspace E2E covers previews, uploads, mutations, and protection. Excel virtualization
and file-upload helpers have Vitest coverage; renderer/cache/backend APIs have Python tests.

## Related Documentation

- [Frontend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
