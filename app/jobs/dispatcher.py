import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import NotificationStatus, OperationalStatus, Role
from app.jobs.notifier import Notice, Notifier
from app.models import Alert, MeasurementPoint, Membership, Notification, User

log = logging.getLogger(__name__)

SEND_TIMEOUT = 10
MAX_RETRY_MINUTES = 30

# Same rule as the evaluator's, and as visible_points for the API.
recipient_can_see_point = or_(
    User.role != Role.CLIENT,
    MeasurementPoint.user_id == User.id,
    MeasurementPoint.organization_id.in_(
        select(Membership.organization_id).where(Membership.user_id == User.id)
    ),
)

NEXT_DUE = (
    select(
        Notification,
        User.phone,
        MeasurementPoint.name.label("point_name"),
        Alert.event_type,
        (
            Alert.is_active
            & (MeasurementPoint.status == OperationalStatus.ACTIVE)
            & recipient_can_see_point
        ).label("still_wanted"),
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

    # Since the notice was queued the alert may have been paused, the point put in testing or
    # its recipient removed from the point's organization; and after an outage there is no point
    # warning about a day that is gone.
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
        # Waits of 1, 2, 4, 8 and 16 minutes, then every half hour. A notice is never given up
        # while it still matters: once its day has passed, dispatch_next skips it.
        minutes = min(2 ** (notification.attempts - 1), MAX_RETRY_MINUTES)
        notification.next_attempt_at = func.now() + timedelta(minutes=minutes)
    else:
        notification.status = NotificationStatus.SENT
        notification.sent_at = func.now()
