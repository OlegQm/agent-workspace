# Frontend Helpers

## Purpose

Own narrowly scoped helpers for safe rendering, file processing, IDs, and virtualization.
Do not add API state or unrelated feature orchestration here.

## Responsibilities

- Sanitize Markdown and normalize safe file references.
- Prepare upload payloads and virtualized spreadsheet windows.
- Generate client operation identifiers and tool display catalogs.

## Entry Points

- [Markdown](markdown.ts)
- [Upload transforms](fileUpload.ts)
- [Visible Excel windows](excelVirtualization.ts)
- [Client IDs](clientId.ts)
- [Tools catalog](toolCatalog.ts)

## Dependencies and Boundaries

Helpers may support components but must not invent authorization or planning states.
Browser-generated operation IDs are not Hermes session IDs. Handle mobile/insecure-origin
capability differences without exposing credentials.

## Tests

Vitest files beside Markdown, upload, virtualization, and localized tool-catalog helpers
cover their contracts. Playwright covers visible integration. Add focused unit tests when
changing a helper.

## Related Documentation

- [Frontend map](../../README.md)
- [Architecture](../../../../docs/architecture.md)
