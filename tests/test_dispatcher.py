import asyncio
from datetime import date

from sqlalchemy import select

from app.enums import EventType, NotificationStatus
from app.jobs.dispatcher import dispatch
from app.jobs.notifier import Notice
from app.models import Notification
from tests.factories import make_alert, make_notification, make_point, make_user
from tests.fakes import RecordingNotifier

DAY = date(2030, 6, 1)


async def pending_notice(session, point_name="La Esperanza", **fields):
    point = await make_point(session, name=point_name)
    alert = await make_alert(session, await make_user(session), point)
    return await make_notification(session, alert, forecast_date=DAY, **fields)


async def statuses(session):
    rows = await session.scalars(select(Notification.status).order_by(Notification.id))
    return list(rows)


async def test_sends_pending_notices_and_marks_them_sent(session):
    user = await make_user(session, phone="+5493415550000")
    alert = await make_alert(session, user, await make_point(session, name="La Esperanza"))
    notification = await make_notification(session, alert, forecast_date=DAY, probability=80)
    notifier = RecordingNotifier()

    assert await dispatch(session, notifier, batch_size=10) == 1

    assert notifier.sent == [Notice("+5493415550000", "La Esperanza", EventType.FROST, DAY, 80)]
    await session.refresh(notification)
    assert notification.status == NotificationStatus.SENT
    assert notification.sent_at is not None


async def test_a_failed_send_is_recorded_and_does_not_stop_the_batch(session):
    await pending_notice(session, point_name="Lote Norte")
    await pending_notice(session, point_name="Lote Sur")
    notifier = RecordingNotifier(failing_points={"Lote Norte"})

    assert await dispatch(session, notifier, batch_size=10) == 2

    assert [notice.point_name for notice in notifier.sent] == ["Lote Sur"]
    assert await statuses(session) == [NotificationStatus.FAILED, NotificationStatus.SENT]


async def test_only_pending_notices_are_sent(session):
    await pending_notice(session, status=NotificationStatus.SENT)
    await pending_notice(session, status=NotificationStatus.FAILED)

    assert await dispatch(session, RecordingNotifier(), batch_size=10) == 0


async def test_sends_at_most_one_batch(session):
    for _ in range(3):
        await pending_notice(session)

    assert await dispatch(session, RecordingNotifier(), batch_size=2) == 2
    assert (await statuses(session)).count(NotificationStatus.PENDING) == 1


async def test_concurrent_dispatchers_never_send_the_same_notice(committed_sessions):
    async with committed_sessions() as session:
        await pending_notice(session)
        await session.commit()

    sending = asyncio.Event()
    release = asyncio.Event()

    class SlowNotifier(RecordingNotifier):
        async def send(self, notice):
            sending.set()
            await release.wait()
            await super().send(notice)

    slow, other = SlowNotifier(), RecordingNotifier()

    async def run(notifier):
        async with committed_sessions() as session, session.begin():
            return await dispatch(session, notifier, batch_size=10)

    first = asyncio.create_task(run(slow))
    await sending.wait()
    try:
        # Without SKIP LOCKED this would wait for the first one to commit.
        assert await asyncio.wait_for(run(other), timeout=2) == 0
    finally:
        release.set()

    assert await first == 1
    assert len(slow.sent) == 1
    assert other.sent == []
