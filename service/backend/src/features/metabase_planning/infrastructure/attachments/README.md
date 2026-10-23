# Planning Attachment Access

## Purpose

Validate attachment references beneath the assigned workspace without ingesting data.
Attachments explain expectations and formulas, not authoritative chart facts.

## Responsibilities

- Require existing regular files within the workspace.
- Preserve safe references for runtime context only.
- Keep attachment content out of review payload construction.

## Entry Points

- [validate_attachment_paths](access.py)
- [Plan provenance validation](../../domain/models.py)

## Dependencies and Boundaries

Path validation does not authorize another user's workspace. Terminal/file inspection
remains allowed inside the assigned sandbox, but values/claims from those files cannot
prove metrics or factual query results. Never forward file content or paths to YouTrack.

## Tests

`tests/features/metabase_planning/infrastructure/attachments/test_access.py` uses temporary
files for valid/invalid paths. Domain and review tests enforce the separate provenance
and outbound payload boundary.

## Related Documentation

- [Planning ownership](../../README.md)
- [File-context boundary](../../../../../../../docs/security.md)
