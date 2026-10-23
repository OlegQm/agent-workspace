# Metabase Planning Feature

## Purpose

Help regular users discover an existing Question or specify one new chart.
Planning does not build a Metabase Question; admin access is read-only.

## Responsibilities

- Persist marked conversations, current requirements/plans, match and review state.
- Validate structured Hermes results and current revisions independently of prose.
- Submit a confirmed plan to one linked YouTrack issue when explicitly enabled.

## Entry Points

- [Planning/match/review HTTP routes](api/router.py)
- [Initial and correction turns](application/turns.py)
- [Validated result application](application/results.py)
- [Review idempotency and safe description](application/reviews.py)

## Dependencies and Boundaries

Hermes chooses when discovery is needed; backend still validates authorized candidates
and current results. Corrections invalidate sendable state/reopen accepted matches.
Review can update one issue, add a revision comment, or recreate a confirmed missing issue.
Status refresh occurs after send, chat opening, or explicit refresh, not background polling.

## Tests

`tests/features/metabase_planning` mirrors API/domain/application/infrastructure.
Fakes cover stale/concurrent submission, retries, missing issue, authorization, and provenance.
Frontend E2E covers real download/navigation contracts through local fake transport.

## Related Documentation

- [hermes](infrastructure/hermes/README.md)
- [youtrack](infrastructure/youtrack/README.md)
- [attachments](infrastructure/attachments/README.md)
- [persistence](infrastructure/persistence/README.md)
- [Planning UI](../../../../frontend/src/features/metabase-planning/README.md)
- [External action enablement](../../../../../docs/configuration.md)
- [Backend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
