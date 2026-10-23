"""Test validated HTTP payloads owned by the workspace slice."""

import pytest
from pydantic import ValidationError

from features.workspace.api.schemas import AccessPolicyBody, FolderBody, RenameBody


def test_workspace_mutation_payloads_preserve_valid_values() -> None:
    """Verify that workspace mutation payloads expose their declared values."""
    assert FolderBody(path="reports").path == "reports"
    assert RenameBody(path="reports/draft.txt", new_name="final.txt").new_name == "final.txt"
    assert AccessPolicyBody(path="private.xlsx", no_user_access=True).no_user_access is True


@pytest.mark.parametrize(
    "factory",
    [
        lambda: FolderBody(path=""),
        lambda: RenameBody(path="reports/file.txt", new_name=""),
    ],
)
def test_workspace_mutation_payloads_reject_empty_paths_or_names(factory) -> None:
    """Verify that workspace mutations cannot be addressed to empty values."""
    with pytest.raises(ValidationError):
        factory()
