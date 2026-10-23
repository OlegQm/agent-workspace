# YouTrack Review Transport

## Purpose

Translate an explicitly approved planning submission into configured tracker operations.
Disabled/incomplete integration must fail closed.

## Responsibilities

- Create or update the linked issue and add a revision comment.
- Read status safely and preserve known state on refresh failure.
- Resolve safe issue URLs against the configured HTTPS origin.

## Entry Points

- [YouTrackReviewClient](client.py)
- [Review policy and title prefix](../../application/reviews.py)
- [Status use case](../../application/status.py)

## Dependencies and Boundaries

Use project ID, resolved assignee user ID, and the configured user custom-field ID,
not arbitrary email/label substitution. The token belongs only in secret configuration.
Transport errors must not expose bodies/credentials or silently duplicate issues.

## Tests

`tests/features/metabase_planning/infrastructure/youtrack/test_client.py` uses fake HTTP
responses. Application tests own idempotency/revision behavior. Live permission preflight
is a separately authorized operator task; no issue is created by local tests.

## Related Documentation

- [Review lifecycle](../../README.md)
- [Enablement checklist](../../../../../../../docs/configuration.md)
