# Administrator Views

## Purpose

Provide separate management UI and read-only conversation inspection/export.
Keep controls consistent with established responsive workspace behavior.

## Responsibilities

- Select a regular user and inspect that user's workspace/history.
- Manage files and inherited protection rules.
- Download authorized conversation JSON without enabling interactive agent chat.

## Entry Points

- [AdminShell](AdminShell.vue)
- [AdminFileBrowser](AdminFileBrowser.vue)
- [AdminConversationBrowser](AdminConversationBrowser.vue)
- [Read-only viewer and export](AdminConversationViewer.vue)

## Dependencies and Boundaries

Only the server's is_admin flag grants entry. Admins may view marked planning chats but
cannot send planning turns, review plans, approve runs, or stop runs. Export requests
must use the protected admin API and preserve download/error/accessibility behavior.

## Tests

Workspace E2E covers desktop/mobile admin browsing and JSON download. Backend workspace
admin/composition tests cover unauthorized users, missing conversations, and real JSON
responses with disposable history.

## Related Documentation

- [Frontend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
