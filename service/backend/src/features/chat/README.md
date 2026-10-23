# Chat Feature

## Purpose

Own ordinary conversations and run transport while preserving private Hermes context.
Planning uses the same display history but has a separate workflow executor.

## Responsibilities

- Create the first conversation/message/run atomically from a browser-local draft.
- Scope reads/deletes/runs by user and agent; stream events and handle approvals/stop.
- Map allowed model modes through agent configuration and persist run metadata.

## Entry Points

- [Conversation/run HTTP routes](api/router.py)
- [Allowed mode names](domain/model_modes.py)
- [ConversationRepository](infrastructure/repositories.py)
- [Hermes runtime adapter](infrastructure/hermes/README.md)

## Dependencies and Boundaries

One active run per agent is enforced in persistence. Never accept a frontend Hermes
session ID or arbitrary provider model ID. Admin history/export belongs to workspace's
admin API and does not permit sending/approving/stopping runs.

## Tests

`tests/features/chat` mirrors API, domain, repositories, and Hermes infrastructure.
Bootstrap composition tests cover cross-feature run lifecycle. Missing initialized runtime
state must fail rather than silently start with empty context.

## Related Documentation

- [Planning workflow](../metabase_planning/README.md)
- [State ownership](../../../../../docs/architecture.md)
- [Backend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
