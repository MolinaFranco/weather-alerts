import asyncio
from datetime import date, timedelta

from sqlalchemy import select

from app.enums import DataStatus, EventType
from app.jobs.evaluator import evaluate, local_today
from app.models import Notification
from tests.factories import make_alert, make_forecast, make_point, make_user

TODAY = date(2030, 6, 1)
STEP = 15


async def notified(session, alert):
    rows = await session.scalars(
        select(Notification.probability)
        .where(Notification.alert_id == alert.id)
        .order_by(Notification.id)
    )
    return list(rows)


async def setup_alert(session, threshold=60, **point_fields):
    point = await make_point(session, **point_fields)
    alert = await make_alert(session, await make_user(session), point, threshold=threshold)
    return point, alert


async def test_notifies_when_the_probability_reaches_the_threshold(session):
    point, alert = await setup_alert(session, threshold=60)
    await make_forecast(session, point, forecast_date=TODAY, probability=60)
    await make_forecast(session, point, forecast_date=TODAY + timedelta(days=1), probability=59)

    assert await evaluate(session, TODAY, STEP) == 1
    assert await notified(session, alert) == [60]


async def test_ignores_other_events_inactive_alerts_and_past_days(session):
    point, alert = await setup_alert(session)
    await make_forecast(
        session, point, forecast_date=TODAY, event_type=EventType.RAIN, probability=90
    )
    await make_forecast(session, point, forecast_date=TODAY - timedelta(days=1), probability=90)
    inactive_point, inactive = await setup_alert(session)
    await make_forecast(session, inactive_point, forecast_date=TODAY, probability=90)
    inactive.is_active = False
    await session.flush()

    assert await evaluate(session, TODAY, STEP) == 0


async def test_ignores_data_that_is_not_active(session):
    testing_point, _ = await setup_alert(session, status=DataStatus.TESTING)
    await make_forecast(session, testing_point, forecast_date=TODAY, probability=90)
    point, _ = await setup_alert(session)
    sample = await make_forecast(session, point, forecast_date=TODAY, probability=90)
    sample.status = DataStatus.DISABLED
    await session.flush()

    assert await evaluate(session, TODAY, STEP) == 0


async def test_a_point_put_in_testing_stops_notifying_its_existing_samples(session):
    point, _ = await setup_alert(session)
    await make_forecast(session, point, forecast_date=TODAY, probability=90)

    point.status = DataStatus.TESTING
    await session.flush()

    assert await evaluate(session, TODAY, STEP) == 0


async def test_running_twice_does_not_notify_twice(session):
    point, alert = await setup_alert(session)
    await make_forecast(session, point, forecast_date=TODAY, probability=70)

    await evaluate(session, TODAY, STEP)
    await evaluate(session, TODAY, STEP)

    assert await notified(session, alert) == [70]


async def test_notifies_again_only_when_the_probability_rises_enough(session):
    point, alert = await setup_alert(session, threshold=60)
    sample = await make_forecast(session, point, forecast_date=TODAY, probability=65)
    await evaluate(session, TODAY, STEP)

    for probability in (79, 50, 80, 90):
        sample.probability = probability
        await session.flush()
        await evaluate(session, TODAY, STEP)

    assert await notified(session, alert) == [65, 80]


async def test_concurrent_evaluations_do_not_duplicate_notices(committed_sessions):
    async with committed_sessions() as session:
        point, alert = await setup_alert(session)
        await make_forecast(session, point, forecast_date=TODAY, probability=70)
        await session.commit()

    async def run_evaluation():
        async with committed_sessions() as session, session.begin():
            return await evaluate(session, TODAY, STEP)

    created = await asyncio.gather(*(run_evaluation() for _ in range(5)))

    assert sum(created) == 1
    async with committed_sessions() as session:
        assert await notified(session, alert) == [70]


def test_today_depends_on_the_timezone():
    # 25 hours apart, so these two never share a date.
    assert local_today("Pacific/Kiritimati") > local_today("Pacific/Pago_Pago")
