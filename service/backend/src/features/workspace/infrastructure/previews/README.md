# Workspace Previews

## Purpose

Render read-only business-document, image, and text previews with bounded private caches.
Preview files are derived UI artifacts, not replacements for originals.

## Responsibilities

- Extract DOCX structure, spreadsheet cells, PDF pages, images, and bounded text.
- Invalidate cache entries when source metadata/content changes.
- Keep cached derivatives outside user-visible workspaces.

## Entry Points

- [Format rendering](rendering.py)
- [PreviewCache](cache.py)
- [Browser preview components](../../../../../../frontend/src/components/files/README.md)

## Dependencies and Boundaries

Settings bound cache age/bytes (default seven days and 2 GiB). PDFs preload pages,
spreadsheets virtualize rows, and large DOCX blocks defer rendering in the UI. Preview
visibility does not imply download permission and is not screen-capture protection.

## Tests

`tests/features/workspace/infrastructure/previews` covers format/error/cache paths using
isolated files. Workspace API tests check authorization; frontend helpers/E2E cover
virtualization and viewer interaction.

## Related Documentation

- [Workspace](../../README.md)
- [Protected previews](../../../../../../../docs/security.md)
