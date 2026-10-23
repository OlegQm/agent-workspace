# Agent Profiles

## Purpose

Declare each agent's identity, runtime endpoints, model profile, and allowed sources.
This configuration is server-authoritative.

## Responsibilities

- Keep IDs, ports, sandbox names, and credential environment names coherent.
- Select enabled integrations and explicit resource allowlists.
- Associate role prompts without placing secrets in versioned YAML.

## Entry Points

- [Neutral assistant profile](assistant.yaml)
- [Manifest schema](schema.json)
- [Prompt ownership](prompts/README.md)
- [Optional code repository aliases](../repositories.yaml)

## Dependencies and Boundaries

The bundled assistant is the only default profile. Its source scopes are empty and fail
closed. Additional agents can be added without feature-code changes, but Compose, source
mounts, image/deployment wiring, and host credentials must also be configured. Model
overrides follow validated precedence.

## Tests

`tests/features/agents/infrastructure/configuration` under backend covers registry,
models, profiles, and rendered Hermes config. Gateway bootstrap tests verify actual
role-specific tool registration rather than assuming the manifest was applied.

## Related Documentation

- [Configuration inventory](../README.md)
- [Overrides and credentials](../../docs/configuration.md)
- [Manifest loader](../../service/backend/src/features/agents/README.md)
