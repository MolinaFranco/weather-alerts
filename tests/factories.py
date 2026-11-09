from datetime import date
from itertools import count

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.enums import EventType
from app.models import (
    Alert,
    MeasurementPoint,
    Membership,
    Notification,
    Organization,
    User,
    WeatherForecast,
)

_sequence = count(1)


def bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def _save[T](session: AsyncSession, instance: T) -> T:
    session.add(instance)
    await session.flush()
    await session.refresh(instance)
    return instance


async def make_user(session: AsyncSession, **fields) -> User:
    n = next(_sequence)
    defaults = {
        "name": f"User {n}",
        "email": f"user{n}@example.com",
        "phone": f"+5491100{n:06d}",
        "password_hash": "not-a-real-hash",
    }
    return await _save(session, User(**defaults | fields))


async def make_organization(session: AsyncSession, **fields) -> Organization:
    return await _save(session, Organization(**{"name": f"Org {next(_sequence)}"} | fields))


async def make_point(session: AsyncSession, **fields) -> MeasurementPoint:
    if "organization_id" not in fields and "user_id" not in fields:
        fields["organization_id"] = (await make_organization(session)).id
    defaults = {"name": f"Point {next(_sequence)}", "latitude": -34.6, "longitude": -58.4}
    return await _save(session, MeasurementPoint(**defaults | fields))


async def make_forecast(
    session: AsyncSession, point: MeasurementPoint, **fields
) -> WeatherForecast:
    defaults = {"forecast_date": date.today(), "event_type": EventType.FROST, "probability": 50}
    return await _save(session, WeatherForecast(point_id=point.id, **defaults | fields))


async def make_alert(session: AsyncSession, user: User, point: MeasurementPoint, **fields) -> Alert:
    defaults = {"event_type": EventType.FROST, "threshold": 60}
    return await _save(session, Alert(user_id=user.id, point_id=point.id, **defaults | fields))


async def make_membership(
    session: AsyncSession, user: User, organization: Organization
) -> Membership:
    return await _save(session, Membership(user_id=user.id, organization_id=organization.id))


async def make_notification(session: AsyncSession, alert: Alert, **fields) -> Notification:
    defaults = {"forecast_date": date.today(), "probability": 70}
    return await _save(session, Notification(alert_id=alert.id, **defaults | fields))
