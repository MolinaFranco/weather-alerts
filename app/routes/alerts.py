from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import get_visible_point, not_found
from app.auth import CurrentUser
from app.db import SessionDep
from app.models import Alert, User
from app.schemas import AlertCreate, AlertOut, AlertUpdate

router = APIRouter(tags=["alerts"])


async def get_own_alert(session: AsyncSession, user: User, alert_id: int) -> Alert:
    alert = await session.scalar(
        select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id)
    )
    if alert is None:
        raise not_found()
    return alert


@router.get("/alerts")
async def list_alerts(user: CurrentUser, session: SessionDep) -> list[AlertOut]:
    alerts = await session.scalars(select(Alert).where(Alert.user_id == user.id).order_by(Alert.id))
    return [AlertOut.model_validate(alert) for alert in alerts]


@router.post("/alerts", status_code=status.HTTP_201_CREATED)
async def create_alert(body: AlertCreate, user: CurrentUser, session: SessionDep) -> AlertOut:
    await get_visible_point(session, user, body.point_id)
    alert = Alert(user_id=user.id, **body.model_dump())
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    return AlertOut.model_validate(alert)


@router.patch("/alerts/{alert_id}")
async def update_alert(
    alert_id: int, body: AlertUpdate, user: CurrentUser, session: SessionDep
) -> AlertOut:
    alert = await get_own_alert(session, user, alert_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(alert, field, value)
    await session.commit()
    return AlertOut.model_validate(alert)


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(alert_id: int, user: CurrentUser, session: SessionDep) -> None:
    await session.delete(await get_own_alert(session, user, alert_id))
    await session.commit()
