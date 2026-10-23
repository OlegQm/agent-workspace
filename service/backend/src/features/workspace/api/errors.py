"""Translate workspace domain failures into stable HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from features.workspace.domain.exceptions import (
    InvalidWorkspacePolicyPath,
    ProtectedWorkspaceMutation,
)


async def invalid_policy_path_handler(
    _request: Request,
    exception: InvalidWorkspacePolicyPath,
) -> JSONResponse:
    """Return the existing bad-request response for an invalid policy path."""
    return JSONResponse(status_code=400, content={"detail": str(exception)})


async def protected_mutation_handler(
    _request: Request,
    exception: ProtectedWorkspaceMutation,
) -> JSONResponse:
    """Return the existing forbidden response for a protected mutation."""
    return JSONResponse(status_code=403, content={"detail": str(exception)})


def configure_workspace_error_handlers(application: FastAPI) -> None:
    """Register transport mappings for workspace domain failures."""
    application.add_exception_handler(InvalidWorkspacePolicyPath, invalid_policy_path_handler)
    application.add_exception_handler(ProtectedWorkspaceMutation, protected_mutation_handler)
