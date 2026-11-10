"""The sync_sample_status trigger, exercised the way the ingestion job writes: upserts."""

from datetime import UTC, date, datetime

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

from app.enums import EventType, OperationalStatus
from app.models import MeasurementPoint, WeatherForecast
from tests.factories import make_forecast, make_point

DAY = date(2030, 6, 1)


async def ingest(session, point, probability, day=DAY):
    statement = insert(WeatherForecast).values(
        point_id=point.id, forecast_date=day, event_type=EventType.FROST, probability=probability
    )
    statement = statement.on_conflict_do_update(
        index_elements=["point_id", "forecast_date", "event_type"],
        set_={"probability": statement.excluded.probability},
    ).returning(WeatherForecast.status)
    return await session.scalar(statement)


async def set_point_status(session, point, status):
    await session.execute(
        update(MeasurementPoint).where(MeasurementPoint.id == point.id).values(status=status)
    )


async def mark_sample(session, point, status):
    return await session.scalar(
        update(WeatherForecast)
        .where(WeatherForecast.point_id == point.id)
        .values(status=status)
        .returning(WeatherForecast.status)
    )


async def test_samples_take_the_status_of_a_point_that_is_not_active(session):
    testing = await make_point(session, status=OperationalStatus.TESTING)
    disabled = await make_point(session, status=OperationalStatus.DISABLED)

    assert await ingest(session, testing, 40) == OperationalStatus.TESTING
    assert await ingest(session, disabled, 40) == OperationalStatus.DISABLED


async def test_new_data_on_a_point_that_was_disabled_is_disabled(session):
    point = await make_point(session)
    await ingest(session, point, 40)

    await set_point_status(session, point, OperationalStatus.DISABLED)

    assert await ingest(session, point, 65) == OperationalStatus.DISABLED


async def test_a_manual_mark_lasts_until_a_new_probability_arrives(session):
    point = await make_point(session)
    await ingest(session, point, 95)

    assert (
        await mark_sample(session, point, OperationalStatus.DISABLED) == OperationalStatus.DISABLED
    )
    assert await ingest(session, point, 95) == OperationalStatus.DISABLED
    assert await ingest(session, point, 30) == OperationalStatus.ACTIVE


async def test_a_sample_cannot_be_activated_while_its_point_is_testing(session):
    point = await make_point(session, status=OperationalStatus.TESTING)
    await ingest(session, point, 40)

    assert await mark_sample(session, point, OperationalStatus.ACTIVE) == OperationalStatus.TESTING


async def test_updates_refresh_updated_at(session):
    point = await make_point(session)
    long_ago = datetime(2000, 1, 1, tzinfo=UTC)
    sample = await make_forecast(session, point, forecast_date=DAY, updated_at=long_ago)

    await ingest(session, point, 80)
    await session.refresh(sample)

    assert sample.updated_at > long_ago


async def test_activating_a_point_activates_its_upcoming_samples(session):
    point = await make_point(session, status=OperationalStatus.TESTING)
    await ingest(session, point, 80)
    await ingest(session, point, 80, day=date(2020, 1, 1))

    await set_point_status(session, point, OperationalStatus.ACTIVE)

    assert await ingest(session, point, 80) == OperationalStatus.ACTIVE
    assert await ingest(session, point, 80, day=date(2020, 1, 1)) == OperationalStatus.TESTING
