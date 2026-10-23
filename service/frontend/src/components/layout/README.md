# Workspace Layout

## Purpose

Arrange conversation navigation, chat, files, and tools for desktop/mobile.
Keep controls consistent with established responsive workspace behavior.

## Responsibilities

- Present persisted history and browser-local drafts.
- Mark planning conversations and provide the planning entry above Tools & data.
- Support drawer navigation and accessible controls without losing active chat selection.

## Entry Points

- [WorkspaceShell](WorkspaceShell.vue)
- [ConversationSidebar](ConversationSidebar.vue)

## Dependencies and Boundaries

Regular and admin shells differ. Layout does not authorize planning or file operations;
server responses decide access. Switching views must preserve draft/type selection and
must not create empty conversations.

## Tests

Workspace and planning E2E cover responsive navigation, draft creation, deletion,
view switching, and planning markers. Use the established desktop/mobile projects.

## Related Documentation

- [Frontend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
