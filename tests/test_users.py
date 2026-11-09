from sqlalchemy import select

from app.enums import Role
from app.models import MeasurementPoint, Membership, User
from tests.factories import bearer, make_organization, make_point, make_user

NEW_USER = {
    "name": "Juan Gómez",
    "email": "juan@example.com",
    "phone": "+5493415550002",
    "password": "a long password",
}


async def test_staff_create_a_client_inside_organizations(client, session):
    technician = await make_user(session, role=Role.TECHNICIAN)
    first, second = await make_organization(session), await make_organization(session)

    response = await client.post(
        "/users",
        headers=bearer(technician),
        json=NEW_USER | {"organization_ids": [first.id, second.id, first.id]},
    )

    assert response.status_code == 201
    assert response.json()["role"] == Role.CLIENT
    memberships = await session.scalars(
        select(Membership.organization_id).where(Membership.user_id == response.json()["id"])
    )
    assert sorted(memberships) == sorted([first.id, second.id])


async def test_creating_a_user_in_a_missing_organization_creates_nothing(client, session):
    technician = await make_user(session, role=Role.TECHNICIAN)

    response = await client.post(
        "/users", headers=bearer(technician), json=NEW_USER | {"organization_ids": [999999]}
    )

    assert response.status_code == 422
    assert await session.scalar(select(User).where(User.email == NEW_USER["email"])) is None


async def test_admins_change_roles_and_delete_users(client, session):
    admin = await make_user(session, role=Role.ADMIN)
    user = await make_user(session)

    promoted = await client.patch(
        f"/users/{user.id}", headers=bearer(admin), json={"role": "technician"}
    )
    deleted = await client.delete(f"/users/{user.id}", headers=bearer(admin))

    assert promoted.status_code == 200
    assert promoted.json()["role"] == Role.TECHNICIAN
    assert deleted.status_code == 204
    assert await session.scalar(select(User).where(User.id == user.id)) is None


async def test_changing_a_missing_user_is_a_404(client, session):
    admin = await make_user(session, role=Role.ADMIN)

    response = await client.patch("/users/999999", headers=bearer(admin), json={"role": "admin"})

    assert response.status_code == 404


async def test_technicians_list_users(client, session):
    technician = await make_user(session, role=Role.TECHNICIAN)
    ana = await make_user(session, name="Ana")

    response = await client.get("/users", headers=bearer(technician))

    assert ana.id in {user["id"] for user in response.json()}


async def test_admins_cant_change_or_delete_their_own_account(client, session):
    admin = await make_user(session, role=Role.ADMIN)

    demoted = await client.patch(
        f"/users/{admin.id}", headers=bearer(admin), json={"role": "client"}
    )
    deleted = await client.delete(f"/users/{admin.id}", headers=bearer(admin))

    assert demoted.status_code == 409
    assert deleted.status_code == 409


async def test_deleting_a_user_removes_their_own_points(client, session):
    admin = await make_user(session, role=Role.ADMIN)
    ana = await make_user(session)
    point = await make_point(session, user_id=ana.id)

    await client.delete(f"/users/{ana.id}", headers=bearer(admin))

    assert (
        await session.scalar(select(MeasurementPoint).where(MeasurementPoint.id == point.id))
        is None
    )
