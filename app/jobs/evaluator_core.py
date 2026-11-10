"""The alert evaluation written with SQLAlchemy's query builder instead of raw SQL.

An equivalent alternative to app/jobs/evaluator.py, and the tests run against both. The
worker uses the raw SQL version because it reads like the query it runs; this one trades
that for column names checked at import time and editor completion.
"""

from datetime import date

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import NotificationStatus, OperationalStatus
from app.jobs.dispatcher import recipient_can_see_point
from app.jobs.evaluator import EVALUATION_LOCK
from app.models import Alert, MeasurementPoint, Notification, User, WeatherForecast


def evaluate_alerts(today: date, step: int):
    notified = (
        select(
            Notification.alert_id,
            Notification.forecast_date,
            func.max(Notification.probability).label("max_probability"),
        )
        .join(Alert, Alert.id == Notification.alert_id)
        .where(
            Notification.forecast_date >= today,
            Notification.status.in_([NotificationStatus.PENDING, NotificationStatus.SENT]),
            Notification.probability >= Alert.threshold,
        )
        .group_by(Notification.alert_id, Notification.forecast_date)
        .cte("notified")
        .prefix_with("MATERIALIZED")
    )
    due = (
        select(Alert.id, WeatherForecast.forecast_date, WeatherForecast.probability)
        .join(User, User.id == Alert.user_id)
        .join(MeasurementPoint, MeasurementPoint.id == Alert.point_id)
        .join(
            WeatherForecast,
            and_(
                WeatherForecast.point_id == Alert.point_id,
                WeatherForecast.event_type == Alert.event_type,
            ),
        )
        .outerjoin(
            notified,
            and_(
                notified.c.alert_id == Alert.id,
                notified.c.forecast_date == WeatherForecast.forecast_date,
            ),
        )
        .where(
            Alert.is_active,
            MeasurementPoint.status == OperationalStatus.ACTIVE,
            WeatherForecast.status == OperationalStatus.ACTIVE,
            recipient_can_see_point,
            WeatherForecast.forecast_date >= today,
            WeatherForecast.probability >= Alert.threshold,
            or_(
                notified.c.max_probability.is_(None),
                WeatherForecast.probability >= notified.c.max_probability + step,
            ),
        )
    )
    return (
        insert(Notification)
        .from_select(["alert_id", "forecast_date", "probability"], due)
        .on_conflict_do_nothing(index_elements=["alert_id", "forecast_date", "probability"])
    )


async def evaluate(session: AsyncSession, today: date, renotify_step: int) -> int:
    """Queue the notices that are due and return how many. Does not commit."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": EVALUATION_LOCK})
    result = await session.execute(evaluate_alerts(today, renotify_step))
    return result.rowcount
