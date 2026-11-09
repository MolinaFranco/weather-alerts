from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth import passwords
from app.config import settings
from app.enums import Role
from tests.factories import bearer, make_membership, make_organization, make_user

NEW_USER = {
    "name": "Ana Pérez",
    "email": "Ana@Example.com",
    "phone": "+5493415550000",
    "password": "a long password",
}


async def test_register_creates_a_client(client):
    response = await client.post("/auth/register", json=NEW_USER)

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == Role.CLIENT
    assert body["email"] == "ana@example.com"
    assert "password" not in body and "password_hash" not in body


async def test_an_email_or_phone_can_only_register_once(client):
    await client.post("/auth/register", json=NEW_USER)
    same_email = NEW_USER | {"email": "ana@example.com", "phone": "+5493415550001"}
    same_phone = NEW_USER | {"email": "otra@example.com"}

    assert (await client.post("/auth/register", json=same_email)).status_code == 409
    assert (await client.post("/auth/register", json=same_phone)).status_code == 409


@pytest.mark.parametrize(
    "field, value",
    [("email", "not-an-email"), ("phone", "341 555-0000"), ("password", "short"), ("name", " ")],
)
async def test_register_rejects_invalid_data(client, field, value):
    response = await client.post("/auth/register", json=NEW_USER | {field: value})

    assert response.status_code == 422


@pytest.mark.parametrize("username", ["ana@example.com", "ANA@example.com", "+5493415550000"])
async def test_login_works_with_email_or_phone(client, session, username):
    await make_user(
        session,
        email="ana@example.com",
        phone="+5493415550000",
        password_hash=passwords.hash("a long password"),
    )

    response = await client.post(
        "/auth/token", data={"username": username, "password": "a long password"}
    )

    assert response.status_code == 200
    token = response.json()["access_token"]
    assert (await client.get("/me", headers={"Authorization": f"Bearer {token}"})).is_success


@pytest.mark.parametrize(
    "username, password",
    [("ana@example.com", "wrong password"), ("nobody@example.com", "a long password")],
)
async def test_login_fails_with_wrong_credentials(client, session, username, password):
    await make_user(
        session, email="ana@example.com", password_hash=passwords.hash("a long password")
    )

    response = await client.post("/auth/token", data={"username": username, "password": password})

    assert response.status_code == 401


async def test_expired_tampered_or_orphan_tokens_are_rejected(client, session):
    user = await make_user(session)
    expired = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.jwt_secret,
        "HS256",
    )
    forged = jwt.encode({"sub": str(user.id)}, "someone-elses-secret-of-32-bytes", "HS256")
    orphan = jwt.encode({"sub": "999999"}, settings.jwt_secret, "HS256")

    for token in (expired, forged, orphan, "not a token"):
        response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


async def test_me_shows_my_organizations(client, session):
    user = await make_user(session)
    mine = await make_organization(session, name="Estancia La Esperanza")
    await make_organization(session, name="Otra")
    await make_membership(session, user, mine)

    response = await client.get("/me", headers=bearer(user))

    assert [o["name"] for o in response.json()["organizations"]] == ["Estancia La Esperanza"]
