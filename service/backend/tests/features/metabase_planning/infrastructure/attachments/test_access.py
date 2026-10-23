"""Test planning attachment workspace boundaries."""

from pathlib import Path

import pytest

from features.metabase_planning.domain.exceptions import InvalidPlanningAttachment
from features.metabase_planning.infrastructure.attachments.access import validate_attachment_paths


@pytest.mark.unit
def test_attachment_validation_rejects_escape_missing_files_and_symlinks(tmp_path: Path) -> None:
    """Allow only regular files physically contained by the assigned workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    workspace.joinpath("link.txt").symlink_to(outside)

    with pytest.raises(InvalidPlanningAttachment, match="outside"):
        validate_attachment_paths(workspace, ["../outside.txt"])
    with pytest.raises(InvalidPlanningAttachment, match="regular file"):
        validate_attachment_paths(workspace, ["missing.txt"])
    with pytest.raises(InvalidPlanningAttachment, match="outside"):
        validate_attachment_paths(workspace, ["link.txt"])
