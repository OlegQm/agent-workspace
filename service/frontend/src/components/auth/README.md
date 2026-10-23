# Authentication Views

## Purpose

Present sign-in without storing passwords or exposing account details.
Keep controls consistent with established responsive workspace behavior.

## Responsibilities

- Collect credentials for the existing session-based auth endpoint.
- Show localized loading/failure state without technical error bodies.
- Return to the authenticated workspace only after server confirmation.

## Entry Points

- [LoginView](LoginView.vue)

## Dependencies and Boundaries

Session cookies are owned by the API/backend. A browser-local view cannot grant a role
or agent binding. Unauthorized API/SSE behavior must clear workspace state. Do not save
passwords, tokens, or authentication screenshots.

## Tests

Workspace E2E covers sign-in and unauthorized flows; identity/bootstrap backend tests
cover authorization. Local E2E uses synthetic credentials and API mocks.

## Related Documentation

- [Frontend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
