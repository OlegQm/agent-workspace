# Agents Feature

## Purpose

Load validated agent manifests/profiles and expose health/capabilities.
Agent identity and resource policy are server-owned, not supplied by the browser.

## Responsibilities

- Resolve manifest paths, validate role/port collisions, and load agent configuration.
- Apply provider/model overrides and render coherent Hermes configuration.
- Probe expected runtime endpoints for authenticated agent health.

## Entry Points

- [Health endpoint](api/router.py)
- [AgentRegistry](infrastructure/configuration/registry.py)
- [LLMProfile and overrides](infrastructure/configuration/llm.py)
- [Hermes config rendering](infrastructure/configuration/hermes.py)

## Dependencies and Boundaries

Configuration models belong to infrastructure, not business domain. Source schemas are
in config/agents. Model-mode identifiers belong to chat domain; concrete provider models
are resolved from the validated profile. Manifest changes also need deployment wiring.

## Tests

`tests/features/agents` mirrors API and configuration ownership. Tests isolate manifest
and data roots and use fake runtime transports. The renderer validates the template
without performing OAuth or external requests.

## Related Documentation

- [Agent manifests](../../../../../config/agents/README.md)
- [Provider configuration](../../../../../docs/configuration.md)
- [Backend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
