import asyncio
from datetime import date, timedelta

from sqlalchemy import func, select, update

from app.enums import EventType, NotificationStatus, OperationalStatus
from app.jobs import dispatcher
from app.jobs.dispatcher import dispatch_next
from app.jobs.notifier import Notice
from app.models import Alert, MeasurementPoint, Notification
from tests.factories import (
    make_alert,
    make_membership,
    make_notification,
    make_organization,
    make_point,
    make_user,
)
from tests.fakes import RecordingNotifier

TODAY = date(2030, 6, 1)


async def queued_notice(session, point_name="La Esperanza", user=None, **fields):
    user = user or await make_user(session)
    point = await make_point(session, name=point_name, user_id=user.id)
    alert = await make_alert(session, user, point)
    return await make_notification(session, alert, **{"forecast_date": TODAY} | fields)


async def make_due_again(session, notification):
    await session.execute(
        update(Notification)
        .where(Notification.id == notification.id)
        .values(next_attempt_at=func.now())
    )


async def test_sends_the_next_due_notice_and_marks_it_sent(session):
    user = await make_user(session, phone="+5493415550000")
    notification = await queued_notice(session, user=user, probability=80)
    notifier = RecordingNotifier()

    assert await dispatch_next(session, notifier, TODAY) is True
    assert await dispatch_next(session, notifier, TODAY) is False

    assert notifier.sent == [Notice("+5493415550000", "La Esperanza", EventType.FROST, TODAY, 80)]
    await session.refresh(notification)
    assert notification.status == NotificationStatus.SENT
    assert notification.sent_at is not None


async def test_sends_the_oldest_notice_first(session):
    await queued_notice(session, point_name="Lote Norte")
    await queued_notice(session, point_name="Lote Sur")
    notifier = RecordingNotifier()

    await dispatch_next(session, notifier, TODAY)

    assert [notice.point_name for notice in notifier.sent] == ["Lote Norte"]


async def test_only_pending_notices_are_sent(session):
    for status in (NotificationStatus.SENT, NotificationStatus.FAILED, NotificationStatus.SKIPPED):
        await queued_notice(session, status=status)
    notifier = RecordingNotifier()

    assert await dispatch_next(session, notifier, TODAY) is False
    assert notifier.sent == []


async def test_skips_notices_that_no_longer_apply(session):
    paused = await queued_notice(session)
    in_testing = await queued_notice(session)
    past_day = await queued_notice(session, forecast_date=TODAY - timedelta(days=1))
    (await session.get(Alert, paused.alert_id)).is_active = False
    testing_alert = await session.get(Alert, in_testing.alert_id)
    (await session.get(MeasurementPoint, testing_alert.point_id)).status = OperationalStatus.TESTING
    await session.flush()
    notifier = RecordingNotifier()

    while await dispatch_next(session, notifier, TODAY):
        pass

    assert notifier.sent == []
    for notification in (paused, in_testing, past_day):
        await session.refresh(notification)
        assert notification.status == NotificationStatus.SKIPPED


async def test_a_failed_send_is_retried_until_its_day_passes(session):
    notification = await queued_notice(session, point_name="Lote Norte")
    notifier = RecordingNotifier(failing_points={"Lote Norte"})
    now = await session.scalar(select(func.now()))

    for attempt, wait in enumerate((1, 2, 4, 8, 16, 30, 30), start=1):
        assert await dispatch_next(session, notifier, TODAY) is True
        await session.refresh(notification)
        assert notification.status == NotificationStatus.PENDING
        assert notification.attempts == attempt
        assert notification.next_attempt_at == now + timedelta(minutes=wait)
        assert await dispatch_next(session, notifier, TODAY) is False, "not due yet"
        await make_due_again(session, notification)

    await dispatch_next(session, notifier, TODAY + timedelta(days=1))
    await session.refresh(notification)
    assert notification.status == NotificationStatus.SKIPPED


async def test_a_send_that_hangs_counts_as_failed(session, monkeypatch):
    monkeypatch.setattr(dispatcher, "SEND_TIMEOUT", 0.05)
    notification = await queued_notice(session)

    class HangingNotifier:
        async def send(self, notice):
            await asyncio.Event().wait()

    assert await dispatch_next(session, HangingNotifier(), TODAY) is True
    await session.refresh(notification)
    assert notification.attempts == 1


async def test_concurrent_dispatchers_split_the_queue(committed_sessions):
    # Both notices belong to the same user: locking only the notification rows is what lets
    # the second worker go ahead instead of waiting on the shared user row.
    async with committed_sessions() as session:
        user = await make_user(session)
        await queued_notice(session, point_name="Lote Norte", user=user)
        await queued_notice(session, point_name="Lote Sur", user=user)
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
            return await dispatch_next(session, notifier, TODAY)

    first = asyncio.create_task(run(slow))
    await asyncio.wait_for(sending.wait(), timeout=2)
    try:
        # Without SKIP LOCKED this would wait for the first one to commit.
        assert await asyncio.wait_for(run(other), timeout=2) is True
    finally:
        release.set()
    assert await first is True

    assert [notice.point_name for notice in slow.sent] == ["Lote Norte"]
    assert [notice.point_name for notice in other.sent] == ["Lote Sur"]


async def test_a_notice_for_someone_who_left_the_organization_is_skipped(session):
    organization = await make_organization(session)
    point = await make_point(session, organization_id=organization.id)
    ana = await make_user(session)
    membership = await make_membership(session, ana, organization)
    notification = await make_notification(
        session, await make_alert(session, ana, point), forecast_date=TODAY
    )
    await session.delete(membership)
    await session.flush()
    notifier = RecordingNotifier()

    await dispatch_next(session, notifier, TODAY)

    assert notifier.sent == []
    await session.refresh(notification)
    assert notification.status == NotificationStatus.SKIPPED
