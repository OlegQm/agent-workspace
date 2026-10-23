# Common Presentation

## Purpose

Share sanitized Markdown presentation, not workspace business state.
Keep controls consistent with established responsive workspace behavior.

## Responsibilities

- Render supported Markdown consistently across ordinary/admin views.
- Delegate sanitization/link handling to established helpers.
- Keep presentation reusable without direct credential or runtime access.

## Entry Points

- [MarkdownContent](MarkdownContent.vue)
- [Markdown parsing/sanitization](../../lib/markdown.ts)

## Dependencies and Boundaries

This directory is not a catch-all for new workflows. Keep feature-specific state and
actions in their ownership areas. All visible text/links must remain safe and accessible;
never enable unrestricted raw HTML.

## Tests

`src/lib/markdown.test.ts` covers parser/sanitizer behavior. Workspace E2E validates
rendered content in ordinary/admin contexts.

## Related Documentation

- [Frontend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
