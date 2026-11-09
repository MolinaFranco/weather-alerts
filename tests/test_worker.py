import asyncio
import logging

from sqlalchemy import select

from app.config import settings
from app.enums import NotificationStatus
from app.loop import local_today, run_until_stopped
from app.models import Notification
from app.worker import run_cycle
from tests.factories import make_alert, make_forecast, make_point, make_user
from tests.fakes import RecordingNotifier


async def test_a_cycle_evaluates_and_sends(committed_sessions):
    async with committed_sessions() as session:
        user = await make_user(session)
        point = await make_point(session, user_id=user.id)
        await make_alert(session, user, point, threshold=60)
        today = local_today(settings.timezone)
        await make_forecast(session, point, forecast_date=today, probability=75)
        await session.commit()
    notifier = RecordingNotifier()

    await run_cycle(committed_sessions, notifier, asyncio.Event())

    assert [notice.probability for notice in notifier.sent] == [75]
    async with committed_sessions() as session:
        assert await session.scalar(select(Notification.status)) == NotificationStatus.SENT


async def test_a_stopping_worker_queues_notices_but_does_not_send_them(committed_sessions):
    async with committed_sessions() as session:
        user = await make_user(session)
        point = await make_point(session, user_id=user.id)
        await make_alert(session, user, point, threshold=60)
        today = local_today(settings.timezone)
        await make_forecast(session, point, forecast_date=today, probability=75)
        await session.commit()
    stop = asyncio.Event()
    stop.set()
    notifier = RecordingNotifier()

    await run_cycle(committed_sessions, notifier, stop)

    assert notifier.sent == []
    async with committed_sessions() as session:
        assert await session.scalar(select(Notification.status)) == NotificationStatus.PENDING


async def test_the_loop_survives_a_failed_cycle():
    stop = asyncio.Event()
    calls = 0

    async def cycle():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("database restarting")
        stop.set()

    await run_until_stopped(stop, cycle, 0, logging.getLogger("test"))

    assert calls == 2


async def test_the_loop_stops_without_waiting_out_the_interval():
    stop = asyncio.Event()

    async def cycle():
        asyncio.get_running_loop().call_later(0.05, stop.set)

    await asyncio.wait_for(run_until_stopped(stop, cycle, 60, logging.getLogger("test")), timeout=1)
