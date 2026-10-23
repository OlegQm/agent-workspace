"""Test workspace access-policy path rules."""

import pytest

from features.workspace.domain.exceptions import InvalidWorkspacePolicyPath
from features.workspace.domain.policies.paths import (
    mutation_touches_protected_path,
    normalize_workspace_path,
    path_is_within,
)


def test_workspace_policy_paths_are_inherited() -> None:
    """Verify that a protected folder also protects all descendants."""
    assert normalize_workspace_path("confidential/report.xlsx") == "confidential/report.xlsx"
    assert path_is_within("confidential/report.xlsx", "confidential")
    assert not path_is_within("public/report.xlsx", "confidential")


def test_upload_next_to_protected_file_is_allowed() -> None:
    """Verify that a protected sibling does not lock the containing folder."""
    protected = ["reports/restricted.xlsx"]

    assert not mutation_touches_protected_path(
        "reports/allowed.xlsx", protected, include_parent=True
    )
    assert mutation_touches_protected_path(
        "reports/restricted.xlsx", protected, include_parent=True
    )


def test_parent_folder_mutation_remains_blocked() -> None:
    """Verify that deleting or renaming a folder cannot remove protected descendants."""
    assert mutation_touches_protected_path("reports", ["reports/restricted.xlsx"])


@pytest.mark.parametrize("path", ["", ".", "..", "../secret", "/absolute"])
def test_workspace_policy_rejects_invalid_paths(path: str) -> None:
    """Verify that policies cannot target a path outside the workspace."""
    with pytest.raises(InvalidWorkspacePolicyPath):
        normalize_workspace_path(path)
