# Hermes Chat Runtime

## Purpose

Adapt the pinned upstream Hermes Sessions/Runs/Events/Approval/Stop APIs.
Keep compactable context in Hermes and complete display history in PostgreSQL.

## Responsibilities

- Create private session mappings and fetch saved transcript for subsequent turns.
- Execute/resume streams, persist events, finalize runs, and recover active tasks.
- Apply configured models and workspace confidentiality around user-visible results.

## Entry Points

- [Runtime orchestration](runtime.py)
- [Concrete profile/model mapping](models.py)
- [Hermes configuration template](../../../../../../../infra/sandbox/hermes-config.template.yaml)

## Dependencies and Boundaries

Internal HTTP calls use the separate Hermes API key, not a source gateway token.
Runtime availability checks use standard endpoints. Do not patch upstream internals,
leak tool payloads through error messages, or replace missing session state silently.

## Tests

`tests/features/chat/infrastructure/hermes` covers transports, errors, persistence,
reconnect/recovery, approvals, cleanup, and model mapping using fakes. Native image
verification is separate from pytest and does not require a real provider login.

## Related Documentation

- [Chat feature](../../README.md)
- [Runtime deployment](../../../../../../../infra/sandbox/README.md)
- [Confidentiality](../../../../../../../docs/security.md)
