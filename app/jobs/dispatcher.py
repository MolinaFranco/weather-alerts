import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import DataStatus, NotificationStatus
from app.jobs.notifier import Notice, Notifier
from app.models import Alert, MeasurementPoint, Notification, User

log = logging.getLogger(__name__)

SEND_TIMEOUT = 10
MAX_ATTEMPTS = 5

NEXT_DUE = (
    select(
        Notification,
        User.phone,
        MeasurementPoint.name.label("point_name"),
        Alert.event_type,
        (Alert.is_active & (MeasurementPoint.status == DataStatus.ACTIVE)).label("still_wanted"),
    )
    .join(Alert, Alert.id == Notification.alert_id)
    .join(User, User.id == Alert.user_id)
    .join(MeasurementPoint, MeasurementPoint.id == Alert.point_id)
    .where(
        Notification.status == NotificationStatus.PENDING,
        Notification.next_attempt_at <= func.now(),
    )
    .order_by(Notification.next_attempt_at, Notification.id)
    .limit(1)
    .with_for_update(of=Notification, skip_locked=True)
)


async def dispatch_next(session: AsyncSession, notifier: Notifier, today: date) -> bool:
    """Send the next due notice. Returns False when none is due.

    Commit after each call. Until then the row stays locked, so other workers skip it, and
    a crash before the commit sends that one notice again: delivery is at least once.
    """
    row = (await session.execute(NEXT_DUE)).one_or_none()
    if row is None:
        return False
    notification = row.Notification

    # The alert may have been paused, or the point put in testing, since the notice was
    # queued; and after an outage there is no point warning about a day that is gone.
    if row.still_wanted and notification.forecast_date >= today:
        notice = Notice(
            row.phone,
            row.point_name,
            row.event_type,
            notification.forecast_date,
            notification.probability,
        )
        await _send(notifier, notification, notice)
    else:
        notification.status = NotificationStatus.SKIPPED
    await session.flush()
    return True


async def _send(notifier: Notifier, notification: Notification, notice: Notice) -> None:
    try:
        async with asyncio.timeout(SEND_TIMEOUT):
            await notifier.send(notice)
    except Exception:
        log.exception("Could not send notification %s", notification.id)
        notification.attempts += 1
        if notification.attempts >= MAX_ATTEMPTS:
            notification.status = NotificationStatus.FAILED
        else:
            # 1, 2, 4 and 8 minutes, so a short outage doesn't use up every attempt.
            delay = timedelta(minutes=2 ** (notification.attempts - 1))
            notification.next_attempt_at = func.now() + delay
    else:
        notification.status = NotificationStatus.SENT
        notification.sent_at = func.now()
