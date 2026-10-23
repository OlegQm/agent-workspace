"""Test HTTP serialization owned by the workspace slice."""

from features.workspace.api.presenters import serialize_file_entries


def test_file_entry_serializer_exposes_effective_access_for_regular_users() -> None:
    """Verify that protected descendants lose download, modification, and copy privileges."""
    entries = [
        {"name": "private.xlsx", "path": "reports/private.xlsx", "type": "file", "size": 1},
        {"name": "reports", "path": "reports", "type": "directory", "size": 0},
    ]

    serialized = serialize_file_entries(entries, ["reports/private.xlsx"], administrator=False)

    assert serialized[0]["no_user_access_explicit"] is True
    assert serialized[0]["can_download"] is False
    assert serialized[1]["preview_kind"] is None


def test_file_entry_serializer_keeps_administrator_workspace_permissions() -> None:
    """Verify that administrators retain management permissions for protected files."""
    serialized = serialize_file_entries(
        [{"name": "private.pdf", "path": "private.pdf", "type": "file", "size": 1}],
        ["private.pdf"],
        administrator=True,
    )

    assert serialized[0]["can_download"] is True
    assert serialized[0]["can_modify"] is True
    assert serialized[0]["can_copy"] is True
