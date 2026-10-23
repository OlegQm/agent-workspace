# Gateway Exports

## Purpose

Write bounded source results beneath the authenticated role's workspace.
Keep these technical facilities independent of specific integrations.

## Responsibilities

- Resolve destination paths/extensions safely.
- Serialize CSV/JSON with source-specific row and byte limits.
- Remove oversize outputs and return relative artifact metadata.

## Entry Points

- [ExportPathResolver](paths.py)
- [TabularExporter](writer.py)

## Dependencies and Boundaries

Exports write local workspace artifacts; they do not mutate connected source systems.
Check destination policy before creating files. Cleanup behavior is format/client-specific;
do not promise atomic writes or general rollback beyond what tests establish.

## Tests

`tests/infrastructure/exports` covers safe paths, extension/row/byte limits, empty data,
serialization, and oversize-file removal with temporary workspaces.

## Related Documentation

- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
