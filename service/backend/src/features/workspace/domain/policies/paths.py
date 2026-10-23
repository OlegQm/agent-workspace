"""Define path rules used by workspace access policies."""

from pathlib import PurePosixPath

from features.workspace.domain.exceptions import InvalidWorkspacePolicyPath


def normalize_workspace_path(value: str) -> str:
    """Normalize a relative workspace path for policy comparisons."""
    path = PurePosixPath(value.strip().replace("\\", "/"))
    if (
        path.is_absolute()
        or not value.strip()
        or path.as_posix() == "."
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise InvalidWorkspacePolicyPath("Invalid policy path")
    return path.as_posix()


def path_is_within(path: str, parent: str) -> bool:
    """Return whether a path is the protected path or one of its descendants."""
    return path == parent or path.startswith(f"{parent}/")


def mutation_touches_protected_path(
    path: str,
    protected: list[str],
    *,
    include_parent: bool = False,
) -> bool:
    """Return whether a user mutation would alter a protected path or subtree."""
    normalized = normalize_workspace_path(path)
    candidates = [normalized]
    if include_parent:
        parent = PurePosixPath(normalized).parent.as_posix()
        if parent != ".":
            candidates.append(parent)
        return any(
            path_is_within(candidate, item) for candidate in candidates for item in protected
        )
    return any(
        path_is_within(normalized, item) or path_is_within(item, normalized) for item in protected
    )
