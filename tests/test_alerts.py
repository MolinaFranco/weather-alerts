from app.enums import DataStatus
from tests.factories import bearer, make_alert, make_point, make_user


async def test_a_client_creates_an_alert_on_a_point_they_see(client, session):
    ana = await make_user(session)
    point = await make_point(session, user_id=ana.id)

    response = await client.post(
        "/alerts",
        headers=bearer(ana),
        json={"point_id": point.id, "event_type": "frost", "threshold": 60},
    )

    assert response.status_code == 201
    assert response.json() | {"id": 0} == {
        "id": 0,
        "point_id": point.id,
        "event_type": "frost",
        "threshold": 60,
        "is_active": True,
    }


async def test_alerts_on_points_you_cant_see_are_a_404(client, session):
    ana = await make_user(session)
    someone_elses = await make_point(session)
    in_testing = await make_point(session, user_id=ana.id, status=DataStatus.TESTING)

    for point in (someone_elses, in_testing):
        response = await client.post(
            "/alerts",
            headers=bearer(ana),
            json={"point_id": point.id, "event_type": "frost", "threshold": 60},
        )
        assert response.status_code == 404


async def test_one_alert_per_point_and_event_with_a_threshold_from_1_to_100(client, session):
    ana = await make_user(session)
    point = await make_point(session, user_id=ana.id)
    alert = {"point_id": point.id, "event_type": "frost", "threshold": 60}
    await client.post("/alerts", headers=bearer(ana), json=alert)

    duplicate = await client.post("/alerts", headers=bearer(ana), json=alert)
    out_of_range = await client.post(
        "/alerts", headers=bearer(ana), json=alert | {"event_type": "rain", "threshold": 0}
    )

    assert duplicate.status_code == 409
    assert out_of_range.status_code == 422


async def test_users_only_see_and_change_their_own_alerts(client, session):
    ana, juan = await make_user(session), await make_user(session)
    point = await make_point(session)
    anas = await make_alert(session, ana, point)
    juans = await make_alert(session, juan, point)

    listed = await client.get("/alerts", headers=bearer(ana))
    paused = await client.patch(
        f"/alerts/{anas.id}", headers=bearer(ana), json={"is_active": False, "threshold": 75}
    )
    not_hers = await client.patch(f"/alerts/{juans.id}", headers=bearer(ana), json={"threshold": 1})
    deleted = await client.delete(f"/alerts/{anas.id}", headers=bearer(ana))

    assert [a["id"] for a in listed.json()] == [anas.id]
    assert paused.json()["is_active"] is False and paused.json()["threshold"] == 75
    assert not_hers.status_code == 404
    assert deleted.status_code == 204
