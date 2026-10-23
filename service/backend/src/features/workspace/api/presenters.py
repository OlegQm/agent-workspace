"""Serialize workspace records for HTTP responses."""

from pathlib import Path

from features.workspace.domain.policies.paths import path_is_within
from features.workspace.infrastructure.previews.rendering import preview_kind


def serialize_file_entries(
    entries: list[dict], protected: list[str], *, administrator: bool
) -> list[dict]:
    """Attach effective access and preview capabilities to file entries."""
    result = []
    for entry in entries:
        restricted = any(path_is_within(entry["path"], path) for path in protected)
        explicit = entry["path"] in protected
        result.append(
            {
                **entry,
                "preview_kind": preview_kind(Path(entry["name"]))
                if entry["type"] == "file"
                else None,
                "no_user_access": restricted,
                "no_user_access_explicit": explicit,
                "no_user_access_inherited": restricted and not explicit,
                "can_download": administrator or not restricted,
                "can_modify": administrator or not restricted,
                "can_copy": administrator or not restricted,
            }
        )
    return result
