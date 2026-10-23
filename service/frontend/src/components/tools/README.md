# Tools and Data View

## Purpose

Explain the authenticated agent's available source tools and scope.
Keep controls consistent with established responsive workspace behavior.

## Responsibilities

- Present the role-aware catalog built from safe server configuration.
- Group available sources with native responsive UI.
- Avoid suggesting credentials alone authorize access.

## Entry Points

- [ToolsPage](ToolsPage.vue)
- [Catalog helpers](../../lib/toolCatalog.ts)

## Dependencies and Boundaries

Do not expose secrets or accept browser-selected role manifests. Tools & data is an
informational view, not a generic source/API proxy. Actual tools are registered and
restricted by Tool Gateway.

## Tests

Workspace E2E covers view navigation and role-aware tool presentation. Gateway bootstrap
contracts cover registered names/schemas/annotations independently of UI labels.

## Related Documentation

- [Frontend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
