import logging

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import NotificationStatus
from app.jobs.notifier import Notice, Notifier
from app.models import Alert, MeasurementPoint, Notification, User

log = logging.getLogger(__name__)

PENDING_NOTICES = (
    select(
        Notification.id,
        User.phone,
        MeasurementPoint.name,
        Alert.event_type,
        Notification.forecast_date,
        Notification.probability,
    )
    .join(Alert, Alert.id == Notification.alert_id)
    .join(User, User.id == Alert.user_id)
    .join(MeasurementPoint, MeasurementPoint.id == Alert.point_id)
    .where(Notification.status == NotificationStatus.PENDING)
    .order_by(Notification.id)
    .with_for_update(of=Notification, skip_locked=True)
)


async def dispatch(session: AsyncSession, notifier: Notifier, batch_size: int) -> int:
    """Send a batch of pending notices and record how each went. Returns the batch size.

    The rows stay locked until the caller commits, so other workers skip them. If the
    process dies before that commit the batch is sent again: delivery is at least once.
    """
    rows = await session.execute(PENDING_NOTICES.limit(batch_size))
    sent, failed = [], []
    for notification_id, *fields in rows:
        try:
            await notifier.send(Notice(*fields))
        except Exception:
            log.exception("Could not send notification %s", notification_id)
            failed.append(notification_id)
        else:
            sent.append(notification_id)

    if sent:
        await session.execute(
            update(Notification)
            .where(Notification.id.in_(sent))
            .values(status=NotificationStatus.SENT, sent_at=func.now())
        )
    if failed:
        await session.execute(
            update(Notification)
            .where(Notification.id.in_(failed))
            .values(status=NotificationStatus.FAILED)
        )
    return len(sent) + len(failed)
