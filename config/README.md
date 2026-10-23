# Configuration Files

## Purpose

Keep versioned, non-secret agent profiles, tool/source policy, and repository inventory.
Ignored environment/runtime files hold secret values.

## Responsibilities

- Declare agents and validate their identities, ports, tools, and LLM profiles.
- Document credential shape without committing credentials.
- Keep Code Sync disabled by default with an empty inventory; add only explicit aliases and upstream branches.

## Entry Points

- [Agent configuration](agents/README.md)
- [Manifest schema](agents/schema.json)
- [Non-secret LLM overrides](llm.env)
- [Credential shape](source-credentials.example.yaml)
- [Repository inventory](repositories.yaml)

## Dependencies and Boundaries

Settings, profiles, and credential payloads are different sources of truth. Manifest
allowlists grant scope; a credential never grants access by itself. Do not add API keys
or real tokens to manifests or the versioned LLM override file.

## Tests

Agent registry/profile tests live under backend agents infrastructure configuration.
Runtime-secret and code-sync tests validate fake payloads/repositories, including an empty default inventory. `task lint`
also validates the rendered Hermes template.

## Related Documentation

- [Configuration guide](../docs/configuration.md)
- [Rendering commands](../scripts/README.md)
- [Agent loading](../service/backend/src/features/agents/README.md)
