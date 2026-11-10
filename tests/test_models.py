from contextlib import asynccontextmanager

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Alert, WeatherForecast
from tests.factories import (
    make_alert,
    make_forecast,
    make_membership,
    make_notification,
    make_organization,
    make_point,
    make_user,
)


@asynccontextmanager
async def rejects(session, constraint):
    with pytest.raises(IntegrityError, match=constraint):
        async with session.begin_nested():
            yield


async def test_point_must_have_exactly_one_owner(session):
    user, organization = await make_user(session), await make_organization(session)

    async with rejects(session, "ck_measurement_points_single_owner"):
        await make_point(session, organization_id=None, user_id=None)
    async with rejects(session, "ck_measurement_points_single_owner"):
        await make_point(session, organization_id=organization.id, user_id=user.id)


async def test_point_names_are_unique_per_owner(session):
    user, organization = await make_user(session), await make_organization(session)
    await make_point(session, organization_id=organization.id, name="La Esperanza")
    await make_point(session, user_id=user.id, name="La Esperanza")

    async with rejects(session, "uq_measurement_points_organization_id_name"):
        await make_point(session, organization_id=organization.id, name="La Esperanza")
    async with rejects(session, "uq_measurement_points_user_id_name"):
        await make_point(session, user_id=user.id, name="La Esperanza")


async def test_point_names_can_repeat_across_owners(session):
    for _ in range(2):
        await make_point(
            session, organization_id=(await make_organization(session)).id, name="Lote 1"
        )
        await make_point(session, user_id=(await make_user(session)).id, name="Lote 1")


async def test_user_email_is_unique_ignoring_case(session):
    await make_user(session, email="ana@example.com")

    async with rejects(session, "uq_users_email_lower"):
        await make_user(session, email="Ana@Example.com")


async def test_user_phone_is_unique_and_in_e164_format(session):
    await make_user(session, phone="+5493415550000")

    async with rejects(session, "uq_users_phone"):
        await make_user(session, phone="+5493415550000")
    async with rejects(session, "ck_users_phone_e164"):
        await make_user(session, phone="341 555-0000")


async def test_a_user_joins_an_organization_once(session):
    user, organization = await make_user(session), await make_organization(session)
    await make_membership(session, user, organization)

    async with rejects(session, "pk_memberships"):
        await make_membership(session, user, organization)


async def test_forecast_probability_is_a_percentage(session):
    point = await make_point(session)

    async with rejects(session, "ck_weather_forecasts_probability_range"):
        await make_forecast(session, point, probability=101)


async def test_one_forecast_per_point_day_and_event(session):
    point = await make_point(session)
    await make_forecast(session, point)

    async with rejects(session, "uq_weather_forecasts_point_id_forecast_date_event_type"):
        await make_forecast(session, point)


async def test_alert_threshold_is_between_1_and_100(session):
    user, point = await make_user(session), await make_point(session)

    async with rejects(session, "ck_alerts_threshold_range"):
        await make_alert(session, user, point, threshold=0)


async def test_one_alert_per_user_point_and_event(session):
    user, point = await make_user(session), await make_point(session)
    await make_alert(session, user, point)

    async with rejects(session, "uq_alerts_user_id_point_id_event_type"):
        await make_alert(session, user, point)


async def test_the_same_notification_is_never_stored_twice(session):
    alert = await make_alert(session, await make_user(session), await make_point(session))
    await make_notification(session, alert, probability=70)
    await make_notification(session, alert, probability=85)

    async with rejects(session, "uq_notifications_alert_id_forecast_date_probability"):
        await make_notification(session, alert, probability=70)


async def test_deleting_a_point_removes_its_forecasts_and_alerts(session):
    point = await make_point(session)
    await make_forecast(session, point)
    await make_alert(session, await make_user(session), point)

    await session.delete(point)
    await session.flush()

    for model in (WeatherForecast, Alert):
        count = await session.scalar(select(func.count()).where(model.point_id == point.id))
        assert count == 0
