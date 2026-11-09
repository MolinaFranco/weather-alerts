from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.auth import CurrentUser
from app.db import SessionDep
from app.models import Alert, Notification
from app.schemas import NotificationOut

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
async def list_notifications(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[NotificationOut]:
    """The user's notices, newest first."""
    notifications = await session.scalars(
        select(Notification)
        .join(Alert)
        .where(Alert.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [NotificationOut.model_validate(n) for n in notifications]
