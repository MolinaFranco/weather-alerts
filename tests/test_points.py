from datetime import date

from app.enums import OperationalStatus, Role
from tests.factories import (
    bearer,
    make_forecast,
    make_membership,
    make_organization,
    make_point,
    make_user,
)

DAY = date(2030, 6, 1)


async def test_clients_see_their_own_and_their_organizations_active_points(client, session):
    ana = await make_user(session)
    organization = await make_organization(session)
    await make_membership(session, ana, organization)
    own = await make_point(session, user_id=ana.id)
    shared = await make_point(session, organization_id=organization.id)
    await make_point(session, organization_id=organization.id, status=OperationalStatus.TESTING)
    await make_point(session, user_id=(await make_user(session)).id)
    await make_point(session)

    response = await client.get("/points", headers=bearer(ana))

    assert sorted(p["id"] for p in response.json()) == sorted([own.id, shared.id])


async def test_staff_see_every_point_in_any_status(client, session):
    technician = await make_user(session, role=Role.TECHNICIAN)
    testing = await make_point(session, status=OperationalStatus.TESTING)

    response = await client.get("/points", headers=bearer(technician))

    assert testing.id in {p["id"] for p in response.json()}


async def test_staff_create_and_update_points(client, session):
    technician = await make_user(session, role=Role.TECHNICIAN)
    organization = await make_organization(session)

    created = await client.post(
        "/points",
        headers=bearer(technician),
        json={
            "name": "Lote Norte",
            "latitude": "-33.123456",
            "longitude": "-60.5",
            "organization_id": organization.id,
        },
    )
    updated = await client.patch(
        f"/points/{created.json()['id']}", headers=bearer(technician), json={"status": "testing"}
    )

    assert created.status_code == 201
    assert created.json()["status"] == OperationalStatus.ACTIVE
    assert updated.json()["status"] == OperationalStatus.TESTING


async def test_a_point_needs_exactly_one_owner(client, session):
    technician = await make_user(session, role=Role.TECHNICIAN)
    point = {"name": "Lote", "latitude": 0, "longitude": 0}

    no_owner = await client.post("/points", headers=bearer(technician), json=point)
    two_owners = await client.post(
        "/points", headers=bearer(technician), json=point | {"organization_id": 1, "user_id": 1}
    )

    assert no_owner.status_code == 422
    assert two_owners.status_code == 422


async def test_clients_only_get_active_samples_and_staff_get_all(client, session):
    ana = await make_user(session)
    technician = await make_user(session, role=Role.TECHNICIAN)
    point = await make_point(session, user_id=ana.id)
    active = await make_forecast(session, point, forecast_date=DAY)
    anomalous = await make_forecast(session, point, forecast_date=date(2030, 6, 2))
    anomalous.status = OperationalStatus.DISABLED
    await session.flush()
    path = f"/points/{point.id}/forecasts"

    seen_by_ana = await client.get(path, headers=bearer(ana))
    seen_by_staff = await client.get(path, headers=bearer(technician))

    assert [f["id"] for f in seen_by_ana.json()] == [active.id]
    assert [f["id"] for f in seen_by_staff.json()] == [active.id, anomalous.id]


async def test_samples_can_be_filtered_by_date(client, session):
    ana = await make_user(session)
    point = await make_point(session, user_id=ana.id)
    for day in (1, 2, 3):
        await make_forecast(session, point, forecast_date=date(2030, 6, day))

    response = await client.get(
        f"/points/{point.id}/forecasts?since=2030-06-02&until=2030-06-02", headers=bearer(ana)
    )

    assert [f["forecast_date"] for f in response.json()] == ["2030-06-02"]


async def test_samples_of_a_point_you_cant_see_are_a_404(client, session):
    ana = await make_user(session)
    someone_elses = await make_point(session)

    response = await client.get(f"/points/{someone_elses.id}/forecasts", headers=bearer(ana))

    assert response.status_code == 404


async def test_marking_a_sample_returns_the_status_the_database_kept(client, session):
    technician = await make_user(session, role=Role.TECHNICIAN)
    point = await make_point(session, status=OperationalStatus.TESTING)
    sample = await make_forecast(session, point, forecast_date=DAY)

    response = await client.patch(
        f"/forecasts/{sample.id}", headers=bearer(technician), json={"status": "active"}
    )

    assert response.json()["status"] == OperationalStatus.TESTING


async def test_admins_delete_points_and_samples(client, session):
    admin = await make_user(session, role=Role.ADMIN)
    point = await make_point(session)
    sample = await make_forecast(session, point, forecast_date=DAY)

    forecast_deleted = await client.delete(f"/forecasts/{sample.id}", headers=bearer(admin))
    point_deleted = await client.delete(f"/points/{point.id}", headers=bearer(admin))
    deleted_again = await client.delete(f"/points/{point.id}", headers=bearer(admin))

    assert forecast_deleted.status_code == 204
    assert point_deleted.status_code == 204
    assert deleted_again.status_code == 404


async def test_a_point_for_a_missing_owner_or_with_a_taken_name_is_refused(client, session):
    technician = await make_user(session, role=Role.TECHNICIAN)
    organization = await make_organization(session)
    await make_point(session, organization_id=organization.id, name="Lote 1")
    point = {"name": "Lote 1", "latitude": 0, "longitude": 0}

    missing_owner = await client.post(
        "/points", headers=bearer(technician), json=point | {"organization_id": 999999}
    )
    taken_name = await client.post(
        "/points", headers=bearer(technician), json=point | {"organization_id": organization.id}
    )

    assert missing_owner.status_code == 422
    assert taken_name.status_code == 409


async def test_a_client_cant_see_their_own_point_while_it_is_in_testing(client, session):
    ana = await make_user(session)
    point = await make_point(session, user_id=ana.id, status=OperationalStatus.TESTING)

    response = await client.get(f"/points/{point.id}/forecasts", headers=bearer(ana))

    assert response.status_code == 404


async def test_an_updated_point_returns_the_coordinates_as_stored(client, session):
    technician = await make_user(session, role=Role.TECHNICIAN)
    point = await make_point(session)

    response = await client.patch(
        f"/points/{point.id}", headers=bearer(technician), json={"latitude": -33.12345678}
    )

    assert response.json()["latitude"] == -33.123457


async def test_a_date_range_that_ends_before_it_starts_is_rejected(client, session):
    ana = await make_user(session)
    point = await make_point(session, user_id=ana.id)

    response = await client.get(
        f"/points/{point.id}/forecasts?since=2030-06-02&until=2030-06-01", headers=bearer(ana)
    )

    assert response.status_code == 422
