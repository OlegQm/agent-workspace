"""Test workspace domain-to-HTTP error translation."""

from types import SimpleNamespace

from fastapi import FastAPI

from features.workspace.api.errors import (
    configure_workspace_error_handlers,
    invalid_policy_path_handler,
    protected_mutation_handler,
)
from features.workspace.domain.exceptions import (
    InvalidWorkspacePolicyPath,
    ProtectedWorkspaceMutation,
)


async def test_workspace_error_handlers_preserve_status_and_detail() -> None:
    """Verify stable HTTP status and body mappings for domain failures."""
    request = SimpleNamespace()
    invalid = await invalid_policy_path_handler(
        request,
        InvalidWorkspacePolicyPath("Invalid policy path"),
    )
    protected = await protected_mutation_handler(
        request,
        ProtectedWorkspaceMutation("protected"),
    )
    assert invalid.status_code == 400 and invalid.body == b'{"detail":"Invalid policy path"}'
    assert protected.status_code == 403 and protected.body == b'{"detail":"protected"}'


def test_workspace_error_handlers_register_on_application() -> None:
    """Verify both workspace domain exceptions are registered."""
    application = FastAPI()
    configure_workspace_error_handlers(application)
    assert InvalidWorkspacePolicyPath in application.exception_handlers
    assert ProtectedWorkspaceMutation in application.exception_handlers
