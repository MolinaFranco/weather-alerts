from app.enums import Role
from tests.factories import bearer, make_membership, make_organization, make_user


async def test_staff_create_an_organization_with_members(client, session):
    technician = await make_user(session, role=Role.TECHNICIAN)
    ana, juan = await make_user(session), await make_user(session)

    created = await client.post(
        "/organizations",
        headers=bearer(technician),
        json={"name": "Estancia La Esperanza", "member_ids": [ana.id, juan.id]},
    )
    members = await client.get(
        f"/organizations/{created.json()['id']}/members", headers=bearer(ana)
    )

    assert created.status_code == 201
    assert sorted(m["id"] for m in members.json()) == sorted([ana.id, juan.id])


async def test_an_organization_can_start_without_members(client, session):
    technician = await make_user(session, role=Role.TECHNICIAN)

    response = await client.post(
        "/organizations", headers=bearer(technician), json={"name": "Campo nuevo"}
    )

    assert response.status_code == 201


async def test_clients_only_see_their_organizations_and_staff_see_all(client, session):
    ana, technician = await make_user(session), await make_user(session, role=Role.TECHNICIAN)
    mine, other = await make_organization(session), await make_organization(session)
    await make_membership(session, ana, mine)

    seen_by_ana = await client.get("/organizations", headers=bearer(ana))
    seen_by_staff = await client.get("/organizations", headers=bearer(technician))
    others_members = await client.get(f"/organizations/{other.id}/members", headers=bearer(ana))

    assert [o["id"] for o in seen_by_ana.json()] == [mine.id]
    assert {mine.id, other.id} <= {o["id"] for o in seen_by_staff.json()}
    assert others_members.status_code == 404


async def test_members_are_added_once_and_can_be_removed(client, session):
    technician = await make_user(session, role=Role.TECHNICIAN)
    ana, organization = await make_user(session), await make_organization(session)
    members = f"/organizations/{organization.id}/members"

    added = await client.post(members, headers=bearer(technician), json={"user_id": ana.id})
    again = await client.post(members, headers=bearer(technician), json={"user_id": ana.id})
    removed = await client.delete(f"{members}/{ana.id}", headers=bearer(technician))
    removed_again = await client.delete(f"{members}/{ana.id}", headers=bearer(technician))

    assert added.status_code == 204
    assert again.status_code == 409
    assert removed.status_code == 204
    assert removed_again.status_code == 404


async def test_adding_to_a_missing_organization_or_a_missing_user_fails(client, session):
    technician = await make_user(session, role=Role.TECHNICIAN)
    ana, organization = await make_user(session), await make_organization(session)

    no_organization = await client.post(
        "/organizations/999999/members", headers=bearer(technician), json={"user_id": ana.id}
    )
    no_user = await client.post(
        f"/organizations/{organization.id}/members",
        headers=bearer(technician),
        json={"user_id": 999999},
    )

    assert no_organization.status_code == 404
    assert no_user.status_code == 422


async def test_staff_rename_and_admins_delete(client, session):
    technician = await make_user(session, role=Role.TECHNICIAN)
    admin = await make_user(session, role=Role.ADMIN)
    organization = await make_organization(session)

    renamed = await client.patch(
        f"/organizations/{organization.id}", headers=bearer(technician), json={"name": "Nuevo"}
    )
    deleted = await client.delete(f"/organizations/{organization.id}", headers=bearer(admin))

    assert renamed.json()["name"] == "Nuevo"
    assert deleted.status_code == 204
