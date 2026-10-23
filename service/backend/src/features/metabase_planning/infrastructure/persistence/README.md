# Planning Persistence

## Purpose

Persist deterministic planning workflow state alongside ordinary conversation history.
UI actions read this state instead of parsing assistant text.

## Responsibilities

- Map requirements/plan/workflow revisions and existing-question candidates.
- Record linked issue identifiers, last submitted revision/time, and operation state.
- Support locking/version checks for corrections and concurrent submissions.

## Entry Points

- [MetabasePlanningState](models.py)
- [Correction invalidation](../../application/turns.py)
- [Submission state transitions](../../application/reviews.py)

## Dependencies and Boundaries

The mapping uses shared database Base and conversation ownership. Initialization imports
feature mappings through application composition. Keep runtime/schema changes separate
from documentation work; production reset is not a compatibility strategy.

## Tests

`tests/features/metabase_planning/infrastructure/persistence/test_models.py` covers mappings.
Application/API tests exercise revision locking, operation retries, status, and deletion
against disposable PostgreSQL.

## Related Documentation

- [Workflow](../../README.md)
- [Database lifecycle](../../../../infrastructure/database/README.md)
