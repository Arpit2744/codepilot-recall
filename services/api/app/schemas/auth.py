"""Authentication schemas."""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# Deliberate RFC-lite validation (no email-validator dependency): the
# authoritative uniqueness key is the normalized lowercased address anyway.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PASSWORD_MIN = 8
PASSWORD_MAX = 128


def _password_rules(v: str) -> str:
    if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
        raise ValueError("password must contain at least one letter and one digit")
    return v


def _email_shape(v: str) -> str:
    if len(v) > 320 or not _EMAIL_RE.match(v):
        raise ValueError("value is not a valid email address")
    return v


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)
    display_name: str | None = Field(default=None, max_length=64)

    check_password = field_validator("password")(_password_rules)
    check_email = field_validator("email")(_email_shape)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)

    check_email = field_validator("email")(_email_shape)


class AuthUser(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    created_at: datetime


class AuthResponse(BaseModel):
    user: AuthUser
    csrf_token: str


class CsrfResponse(BaseModel):
    csrf_token: str


class SessionInfo(BaseModel):
    id: uuid.UUID
    issued_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    created_via: str
    current: bool = False


class SessionListResponse(BaseModel):
    sessions: list[SessionInfo]


class RevokeAllResponse(BaseModel):
    revoked: int
