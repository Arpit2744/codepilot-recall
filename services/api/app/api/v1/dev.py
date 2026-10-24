"""DEVELOPMENT ONLY: bootstrap helper behind the Phase 1 dev auth boundary.

Registration arrives in Phase 5. Until then, local/UI development needs a way
to materialize a user row so the X-User-Id dev header can reference it. This
endpoint refuses to exist in production and creates zero privileges.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models import User

router = APIRouter(prefix="/dev", tags=["dev"])


class CreateDevUserRequest(BaseModel):
    display_name: str | None = None


class DevUserResponse(BaseModel):
    user_id: str
    email: str
    display_name: str


@router.post("/users", response_model=DevUserResponse, status_code=201)
def create_dev_user(
    payload: CreateDevUserRequest | None = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    settings = get_settings()
    if settings.environment == "production":
        raise HTTPException(status_code=404, detail="Not Found")

    import uuid

    suffix = uuid.uuid4().hex[:8]
    display_name = (payload.display_name if payload and payload.display_name else "Developer")[:64]
    user = User(email=f"dev-{suffix}@example.com", display_name=display_name)
    db.add(user)
    db.commit()
    return DevUserResponse(user_id=str(user.id), email=user.email, display_name=user.display_name)
