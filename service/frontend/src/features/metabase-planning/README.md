# Metabase Planning UI

## Purpose

Present one-chart requirements discovery and explicit review without building Questions.
The entry is for regular users only; admins use the read-only history viewer.

## Responsibilities

- Display collecting/match/plan/review state from server responses.
- Confirm Send/Update for review, handle concurrent/stale actions, and show linked status.
- Open authorized Metabase/tracker navigation in a new tab.

## Entry Points

- [PlanningPanel](components/PlanningPanel.vue)
- [Review confirmation](components/ReviewConfirmationDialog.vue)
- [Planning state/action orchestration](../../composables/useWorkspace.ts)

## Dependencies and Boundaries

Do not parse assistant prose to enable buttons. Corrections invalidate the sendable plan
and reopen accepted matches. Preserve known issue status on refresh failure and do not
poll tracker status continuously. File context is not authoritative chart data.

## Tests

`e2e/metabase-planning.spec.ts` checks state/actions/authorization and responsive behavior
with fake transport. Backend planning tests own revisions, provenance, persistence,
matching, and tracker failure/idempotency rules.

## Related Documentation

- [Backend planning](../../../../backend/src/features/metabase_planning/README.md)
- [Fail-closed external enablement](../../../../../docs/configuration.md)
- [Frontend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
