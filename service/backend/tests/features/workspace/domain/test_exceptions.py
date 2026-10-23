"""Test transport-independent workspace exceptions."""

from features.workspace.domain.exceptions import (
    InvalidWorkspacePolicyPath,
    ProtectedWorkspaceMutation,
)


def test_workspace_exceptions_expose_semantic_standard_bases() -> None:
    """Preserve value and permission semantics without transport dependencies."""
    assert isinstance(InvalidWorkspacePolicyPath("invalid"), ValueError)
    assert isinstance(ProtectedWorkspaceMutation("protected"), PermissionError)
