# Gateway Audit

## Purpose

Record structured tool execution metadata without tool results or credentials.
Keep these technical facilities independent of specific integrations.

## Responsibilities

- Decorate synchronous and asynchronous tool calls.
- Record safe success/failure metadata and duration.
- Keep audit output scoped by gateway role.

## Entry Points

- [AuditRecorder](audit.py)

## Dependencies and Boundaries

Audit is diagnostic metadata, not a copy of business results. Avoid adding arguments,
response bodies, tokens, or file content to records. Failure auditing must preserve the
underlying tool error behavior.

## Tests

`tests/infrastructure/observability/test_audit.py` covers sync/async success and failure.
Use temporary output paths and synthetic tool invocations.

## Related Documentation

- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
