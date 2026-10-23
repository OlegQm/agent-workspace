"""Resolve planning attachment references inside one assigned workspace."""

from pathlib import Path

from features.metabase_planning.domain.exceptions import InvalidPlanningAttachment


def validate_attachment_paths(workspace_root: Path, attachments: list[str]) -> list[str]:
    """Validate regular non-symlink files without reading or copying their contents."""
    root = workspace_root.resolve()
    validated: list[str] = []
    for relative in attachments:
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise InvalidPlanningAttachment("Attachment is outside the workspace") from exc
        if not candidate.is_file() or candidate.is_symlink():
            raise InvalidPlanningAttachment(f"Attachment is not a regular file: {relative}")
        validated.append(Path(relative).as_posix())
    return validated
