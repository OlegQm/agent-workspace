# ClickUp Integration

## Purpose

Read role-allowed workspaces/lists, tasks, custom fields, and task attachments.
Expose only the manifest-enabled MCP contract.

## Responsibilities

- Navigate spaces, folders, and lists within explicit workspace scope.
- Fetch bounded paginated tasks and custom fields.
- Validate task-owned attachments before local download.

## Entry Points

- [register_tools: names, signatures, descriptions](api/tools.py)
- [Application service](application/service.py)
- [Concrete source client](infrastructure/client.py)

## Dependencies and Boundaries

Each role has its own token and Workspace/List allowlists. Attachment URLs are subject
to host/redirect/resource checks; local downloads are not upstream writes. Do not add a
generic URL download or task-mutation escape hatch.
API registrars delegate to application services; bootstrap injects client dependencies.

## Tests

`tests/integrations/clickup` mirrors API/application/infrastructure (and domain where
present). Tests fake SDK/HTTP/Git behavior and assert success/error contracts. Gateway
bootstrap tests verify role-specific registration, schemas, and annotations.

## Related Documentation

- [Gateway map](../../../../README.md)
- [Security](../../../../../../docs/security.md)
- [Credentials and scopes](../../../../../../docs/configuration.md)
