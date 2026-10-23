# Workspace Orchestration

## Purpose

Coordinate authentication, current user/agent, conversations, runs, files, and planning.
This is existing frontend state ownership, not a new shared business layer.

## Responsibilities

- Initialize/clear authenticated workspace state and drafts.
- Stream/reconnect runs and map server results into visible UI state.
- Coordinate planning navigation, safe review actions, and explicit status refresh.

## Entry Points

- [useWorkspace](useWorkspace.ts)
- [HTTP/SSE contracts](../api.ts)

## Dependencies and Boundaries

Standard run streaming and planning workflow state are separate. Button availability
comes from persisted server contracts. No continuous tracker-status polling is permitted;
refresh only after successful review, chat opening, or explicit request.

## Tests

Workspace/planning E2E exercise behavior through fake API transport on desktop/mobile.
`npm run typecheck` validates the shared contracts. Do not use real source credentials
or a live app URL for the standard test suite.

## Related Documentation

- [Planning UI](../features/metabase-planning/README.md)
- [Frontend map](../../README.md)
- [Architecture](../../../../docs/architecture.md)
