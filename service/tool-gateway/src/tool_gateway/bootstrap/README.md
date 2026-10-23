# Gateway Bootstrap

## Purpose

Compose manifest-selected settings, shared infrastructure, concrete clients, and MCP registrars.
This is the only place that selects enabled integration implementations.

## Responsibilities

- Construct clients/services through constructor DI.
- Validate gateway identity and source environment before application registration.
- Pass audit/export/limit dependencies to enabled integrations.

## Entry Points

- [build_container](container.py)
- [build_application](application.py)

## Dependencies and Boundaries

Only manifest-enabled services are instantiated/registered. Integrations and shared
infrastructure must not import bootstrap. Server entrypoint import composes the app;
provide fake settings before importing it in tests.

## Tests

`tests/bootstrap` covers container selection, manifest validation, and the bundled assistant's
complete tool contract.
Contract tests belong here because they inspect composition across integrations.
SDK/network dependencies are replaced with fakes.

## Related Documentation

- [Gateway map](../../../README.md)
- [Security](../../../../../docs/security.md)
