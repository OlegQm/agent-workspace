"""Define workspace policy failures without transport dependencies."""


class InvalidWorkspacePolicyPath(ValueError):
    """Signal that a workspace policy path is not a safe relative path."""


class ProtectedWorkspaceMutation(PermissionError):
    """Signal that a user mutation would alter protected workspace content."""
