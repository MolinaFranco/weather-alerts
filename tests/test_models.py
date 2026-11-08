from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.enums import DataStatus
from tests.factories import make_alert, make_forecast, make_point, make_user


async def assert_rejected(session, factory, constraint, *args, **fields):
    with pytest.raises(IntegrityError, match=constraint):
        async with session.begin_nested():
            await factory(session, *args, **fields)


async def test_point_must_have_exactly_one_owner(session):
    user = await make_user(session)
    point = await make_point(session)

    await assert_rejected(session, make_point, "single_owner", organization_id=None)
    await assert_rejected(
        session, make_point, "single_owner", organization_id=point.organization_id, user_id=user.id
    )


async def test_point_names_are_unique_per_owner(session):
    point = await make_point(session)

    await assert_rejected(
        session,
        make_point,
        "uq_measurement_points_organization_id_name",
        organization_id=point.organization_id,
        name=point.name,
    )


async def test_forecast_probability_is_a_percentage(session):
    point = await make_point(session)

    await assert_rejected(session, make_forecast, "probability_range", point, probability=101)


async def test_one_forecast_per_point_day_and_event(session):
    point = await make_point(session)
    await make_forecast(session, point)

    await assert_rejected(session, make_forecast, "uq_weather_forecasts", point)


async def test_alert_threshold_is_between_1_and_100(session):
    user, point = await make_user(session), await make_point(session)

    await assert_rejected(session, make_alert, "threshold_range", user, point, threshold=0)


async def test_one_alert_per_user_point_and_event(session):
    user, point = await make_user(session), await make_point(session)
    await make_alert(session, user, point)

    await assert_rejected(session, make_alert, "uq_alerts", user, point)


async def test_samples_from_a_testing_point_stay_testing_after_activation(session):
    point = await make_point(session, status=DataStatus.TESTING)
    test_sample = await make_forecast(session, point, probability=40)

    point.status = DataStatus.ACTIVE
    await session.flush()
    test_sample.probability = 45
    await session.flush()
    await session.refresh(test_sample)
    real_sample = await make_forecast(session, point, forecast_date=date(2030, 1, 1))

    assert test_sample.status == DataStatus.TESTING
    assert real_sample.status == DataStatus.ACTIVE


async def test_samples_from_a_disabled_point_are_disabled(session):
    point = await make_point(session, status=DataStatus.DISABLED)

    sample = await make_forecast(session, point)

    assert sample.status == DataStatus.DISABLED
