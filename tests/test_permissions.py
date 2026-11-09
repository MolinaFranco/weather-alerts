import pytest

from app.enums import Role
from tests.factories import bearer, make_user

TECHNICIAN_ONLY = [
    ("GET", "/users"),
    ("POST", "/users"),
    ("POST", "/organizations"),
    ("PATCH", "/organizations/1"),
    ("POST", "/organizations/1/members"),
    ("DELETE", "/organizations/1/members/1"),
    ("POST", "/points"),
    ("PATCH", "/points/1"),
    ("PATCH", "/forecasts/1"),
]
ADMIN_ONLY = [
    ("PATCH", "/users/1"),
    ("DELETE", "/users/1"),
    ("DELETE", "/organizations/1"),
    ("DELETE", "/points/1"),
    ("DELETE", "/forecasts/1"),
]
ANY_USER = [
    ("GET", "/me"),
    ("GET", "/organizations"),
    ("GET", "/organizations/1/members"),
    ("GET", "/points"),
    ("GET", "/points/1/forecasts"),
    ("GET", "/alerts"),
    ("POST", "/alerts"),
    ("PATCH", "/alerts/1"),
    ("DELETE", "/alerts/1"),
    ("GET", "/notifications"),
]


@pytest.mark.parametrize(
    ("role", "method", "path"),
    [(Role.CLIENT, *endpoint) for endpoint in TECHNICIAN_ONLY]
    + [(Role.TECHNICIAN, *endpoint) for endpoint in ADMIN_ONLY],
)
async def test_a_role_below_the_minimum_is_forbidden(client, session, role, method, path):
    user = await make_user(session, role=role)

    response = await client.request(method, path, headers=bearer(user), json={})

    assert response.status_code == 403


@pytest.mark.parametrize(("method", "path"), TECHNICIAN_ONLY + ADMIN_ONLY + ANY_USER)
async def test_every_route_but_login_needs_a_token(client, method, path):
    response = await client.request(method, path, json={})

    assert response.status_code == 401
