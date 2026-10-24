"""Request dependencies.

DEVELOPMENT AUTHENTICATION BOUNDARY (Phase 1):
Real session auth lands in Phase 5. Until then, non-production environments
resolve the current user from an explicit `X-User-Id` header that must
reference an existing user. Production environments reject every request —
safe by default; there is deliberately NO fallback identity.

This is a documented development boundary, NOT an authentication mechanism:
any local client can impersonate any user id, so it must never be deployed.
"""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.repositories.codeforces import get_user

DEV_AUTH_HEADER = "X-User-Id"


def get_current_user_id(request: Request, db: Annotated[Session, Depends(get_db)]) -> uuid.UUID:
    settings = get_settings()
    if settings.environment == "production":
        raise HTTPException(
            status_code=401,
            detail="Authentication is not available until Phase 5; "
            "this deployment must not serve user data.",
        )

    raw = request.headers.get(DEV_AUTH_HEADER)
    if not raw:
        raise HTTPException(status_code=401, detail=f"Missing {DEV_AUTH_HEADER} header")
    try:
        user_id = uuid.UUID(raw)
    except ValueError:
        raise HTTPException(status_code=401, detail=f"Invalid {DEV_AUTH_HEADER} header") from None

    if get_user(db, user_id) is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user_id
