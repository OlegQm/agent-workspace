"""Define validated HTTP payloads owned by the identity API."""

from pydantic import BaseModel, Field


class LoginBody(BaseModel):
    """Represent the validated login request payload."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)
