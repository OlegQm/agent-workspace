# Chat Components

## Purpose

Render persisted messages and ordinary run interactions.
Keep controls consistent with established responsive workspace behavior.

## Responsibilities

- Display sanitized Markdown, tool timeline, and configured model modes.
- Compose messages/uploads and expose approval/stop controls.
- Show streaming/loading/errors without inferring planning workflow from text.

## Entry Points

- [ChatPanel](ChatPanel.vue)
- [MessageComposer](MessageComposer.vue)
- [MessageBubble](MessageBubble.vue)
- [RunTimeline](RunTimeline.vue)
- [ModelModeSelector](ModelModeSelector.vue)

## Dependencies and Boundaries

The workspace composable owns API/state orchestration. Model choices are server-provided
modes, not arbitrary model IDs. Presentation must not render raw HTML or turn internal
file/URL references into unauthorized downloads.

## Tests

Workspace and planning Playwright suites check desktop/mobile conversation behavior.
Markdown/helper unit tests cover safe rendering and upload transforms.

## Related Documentation

- [Frontend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
