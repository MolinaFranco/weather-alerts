import asyncio
from datetime import date, timedelta

from sqlalchemy import select, update

from app.enums import DataStatus, EventType
from app.jobs.evaluator import evaluate, local_today
from app.models import Notification, WeatherForecast
from tests.factories import make_alert, make_forecast, make_point, make_user

TODAY = date(2030, 6, 1)
TOMORROW = TODAY + timedelta(days=1)
STEP = 15


async def notified(session, alert):
    rows = await session.scalars(
        select(Notification.probability)
        .where(Notification.alert_id == alert.id)
        .order_by(Notification.id)
    )
    return list(rows)


async def watched_point(session, **point_fields):
    """A point with a frost alert at 60% from a new user."""
    point = await make_point(session, **point_fields)
    alert = await make_alert(session, await make_user(session), point, threshold=60)
    return point, alert


async def test_notifies_when_the_probability_reaches_the_threshold(session):
    point, alert = await watched_point(session)
    await make_forecast(session, point, forecast_date=TODAY, probability=60)
    await make_forecast(session, point, forecast_date=TOMORROW, probability=59)

    assert await evaluate(session, TODAY, STEP) == 1
    assert await notified(session, alert) == [60]


async def test_ignores_other_events(session):
    point, _ = await watched_point(session)
    await make_forecast(
        session, point, forecast_date=TODAY, event_type=EventType.RAIN, probability=90
    )

    assert await evaluate(session, TODAY, STEP) == 0


async def test_ignores_past_days(session):
    point, _ = await watched_point(session)
    await make_forecast(session, point, forecast_date=TODAY - timedelta(days=1), probability=90)

    assert await evaluate(session, TODAY, STEP) == 0


async def test_ignores_inactive_alerts(session):
    point, alert = await watched_point(session)
    await make_forecast(session, point, forecast_date=TODAY, probability=90)
    alert.is_active = False
    await session.flush()

    assert await evaluate(session, TODAY, STEP) == 0


async def test_ignores_data_that_is_not_active(session):
    testing_point, _ = await watched_point(session, status=DataStatus.TESTING)
    await make_forecast(session, testing_point, forecast_date=TODAY, probability=90)
    point, _ = await watched_point(session)
    sample = await make_forecast(session, point, forecast_date=TODAY, probability=90)
    sample.status = DataStatus.DISABLED
    await session.flush()

    assert await evaluate(session, TODAY, STEP) == 0


async def test_a_point_put_in_testing_stops_notifying_its_existing_samples(session):
    point, _ = await watched_point(session)
    await make_forecast(session, point, forecast_date=TODAY, probability=90)

    point.status = DataStatus.TESTING
    await session.flush()

    assert await evaluate(session, TODAY, STEP) == 0


async def test_running_twice_does_not_notify_twice(session):
    point, alert = await watched_point(session)
    await make_forecast(session, point, forecast_date=TODAY, probability=70)

    assert await evaluate(session, TODAY, STEP) == 1
    assert await evaluate(session, TODAY, STEP) == 0
    assert await notified(session, alert) == [70]


async def test_notifies_again_only_when_the_probability_rises_enough(session):
    point, alert = await watched_point(session)
    sample = await make_forecast(session, point, forecast_date=TODAY, probability=65)
    await evaluate(session, TODAY, STEP)

    for probability in (79, 50, 80, 90):
        sample.probability = probability
        await session.flush()
        await evaluate(session, TODAY, STEP)

    assert await notified(session, alert) == [65, 80]


async def test_each_day_is_notified_on_its_own(session):
    point, alert = await watched_point(session)
    await make_forecast(session, point, forecast_date=TODAY, probability=70)
    await make_forecast(session, point, forecast_date=TOMORROW, probability=72)

    await evaluate(session, TODAY, STEP)

    assert sorted(await notified(session, alert)) == [70, 72]


async def test_raising_the_threshold_rearms_the_alert(session):
    point, alert = await watched_point(session)
    sample = await make_forecast(session, point, forecast_date=TODAY, probability=65)
    await evaluate(session, TODAY, STEP)

    alert.threshold = 70
    sample.probability = 72
    await session.flush()
    await evaluate(session, TODAY, STEP)

    assert await notified(session, alert) == [65, 72]


async def test_a_reactivated_alert_does_not_repeat_a_notice(session):
    point, alert = await watched_point(session)
    await make_forecast(session, point, forecast_date=TODAY, probability=70)
    await evaluate(session, TODAY, STEP)

    alert.is_active = False
    await session.flush()
    alert.is_active = True
    await session.flush()

    assert await evaluate(session, TODAY, STEP) == 0


async def test_every_user_watching_a_point_is_notified(session):
    point, first = await watched_point(session)
    second = await make_alert(session, await make_user(session), point)
    await make_forecast(session, point, forecast_date=TODAY, probability=70)

    await evaluate(session, TODAY, STEP)

    assert await notified(session, first) == [70]
    assert await notified(session, second) == [70]


async def test_evaluations_take_turns(committed_sessions):
    # Reproduces the race the advisory lock prevents: without it, the second run would not
    # see the first run's uncommitted 70 and would notify 75, a rise smaller than the step.
    async with committed_sessions() as session:
        point, alert = await watched_point(session)
        sample = await make_forecast(session, point, forecast_date=TODAY, probability=70)
        await session.commit()

    async def second_run():
        async with committed_sessions() as session, session.begin():
            return await evaluate(session, TODAY, STEP)

    async with committed_sessions() as first:
        assert await evaluate(first, TODAY, STEP) == 1
        async with committed_sessions() as ingestion, ingestion.begin():
            await ingestion.execute(
                update(WeatherForecast)
                .where(WeatherForecast.id == sample.id)
                .values(probability=75)
            )
        second = asyncio.create_task(second_run())
        await asyncio.sleep(0.2)
        assert not second.done()
        await first.commit()

    assert await second == 0
    async with committed_sessions() as session:
        assert await notified(session, alert) == [70]


def test_today_depends_on_the_timezone():
    # 25 hours apart, so these two never share a date.
    assert local_today("Pacific/Kiritimati") > local_today("Pacific/Pago_Pago")
