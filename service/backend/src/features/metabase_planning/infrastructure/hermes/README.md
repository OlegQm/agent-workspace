# Hermes Planner Adapter

## Purpose

Run a dedicated planning turn with ordinary workspace terminal/file capabilities.
Separate safe user-facing prose from the structured workflow result.

## Responsibilities

- Inject the role planner prompt and precise JSON contract.
- Parse/validate Pydantic output and retry malformed structure once.
- Persist only validated current results and show safe failures instead of raw validation errors.

## Entry Points

- [Planning executor](executor.py)
- [PlannerResult parser/schema](contracts.py)
- [Role planner prompts](../../../../../../../config/agents/prompts/README.md)

## Dependencies and Boundaries

Discovery uses authorized read-only tools. Terminal/files may explain context/formulas
but cannot make their values authoritative business inputs. No file content, paths,
excerpts, secrets, or derivatives belong in the review payload. No Hermes internals are patched.

## Tests

`tests/features/metabase_planning/infrastructure/hermes` covers contract parsing, retry,
state application, runtime errors, and safe messages with fake Hermes responses.
Do not treat a fake test as evidence of live provider/tool availability.

## Related Documentation

- [Planning feature](../../README.md)
- [Shared runtime](../../../chat/infrastructure/hermes/README.md)
- [Provenance](../../../../../../../docs/security.md)
