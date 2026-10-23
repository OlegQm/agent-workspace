# Agent Instructions

## Purpose

Keep assistant SOUL and Metabase planner instructions versioned in English.
These are runtime instructions, separate from repository contributor instructions.

## Responsibilities

- Describe source authority, tool selection, business context, and verification.
- Constrain planning to discovery/requirements rather than creating Questions.
- Preserve file-context provenance and safe tracker payload rules.

## Entry Points

- [Assistant SOUL](assistant/SOUL.md)
- [Assistant Metabase planner](assistant/METABASE_PLANNER.md)

## Dependencies and Boundaries

`task runtime:prepare` synchronizes existing agent-private runtime configuration/SOUL;
backend turn construction injects current instructions. Agents answer in the user's
language. Prompt instructions complement but never replace authorization, schema
validation, resource allowlists, or deterministic workflow state.

## Tests

Backend executor/runtime tests inspect prompt/context and structured-result handling.
Manually review both role prompts after changing source semantics; local tests cannot
prove an LLM always follows prose. Never embed real credentials or private dumps.

## Related Documentation

- [Profiles](../README.md)
- [Planning contract](../../../service/backend/src/features/metabase_planning/README.md)
- [Coding-agent documentation review](../../../.agents/AGENTS.md)
