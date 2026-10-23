# Code Snapshots Integration

## Purpose

Expose bounded read-only inspection of configured repository snapshots.
Expose only the manifest-enabled MCP contract.

## Responsibilities

- List/status/tree/search/read files and inspect reachable commit history.
- Support log, show, blame, and diff within configured branches.
- Block secret paths, binary content, and write-capable commands.

## Entry Points

- [register_tools: names, signatures, descriptions](api/tools.py)
- [Application service](application/service.py)
- [Concrete source client](infrastructure/client.py)

## Dependencies and Boundaries

Snapshots come from optional Code Sync; the default assistant has no repository aliases
enabled, and this client never receives the Git token. Only reachable
revisions and configured aliases are accepted. Search/path/subprocess limits do not
turn an arbitrary external checkout into an approved code source.
API registrars delegate to application services; bootstrap injects client dependencies.

## Tests

`tests/integrations/code` mirrors API/application/infrastructure (and domain where
present). Tests fake SDK/HTTP/Git behavior and assert success/error contracts. Gateway
bootstrap tests verify role-specific registration, schemas, and annotations.

## Related Documentation

- [Snapshot producer](../../../../../code-sync/README.md)
- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
- [Credentials and scopes](../../../../../../docs/configuration.md)
