"""Define validated HTTP payloads owned by the workspace API."""

from pydantic import BaseModel, Field


class FolderBody(BaseModel):
    """Represent a workspace folder creation request."""

    path: str = Field(min_length=1, max_length=500)


class RenameBody(BaseModel):
    """Represent a workspace file or folder rename request."""

    path: str = Field(min_length=1, max_length=500)
    new_name: str = Field(min_length=1, max_length=255)


class AccessPolicyBody(BaseModel):
    """Represent an administrator workspace access-policy request."""

    path: str = Field(min_length=1, max_length=500)
    no_user_access: bool
