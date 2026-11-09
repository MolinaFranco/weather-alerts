from datetime import UTC, date, datetime

from tests.factories import bearer, make_alert, make_notification, make_point, make_user


async def test_notifications_are_mine_newest_first_and_paged(client, session):
    ana, juan = await make_user(session), await make_user(session)
    point = await make_point(session)
    anas, juans = await make_alert(session, ana, point), await make_alert(session, juan, point)
    notices = [
        await make_notification(
            session,
            anas,
            forecast_date=date(2030, 6, day),
            created_at=datetime(2030, 5, 31, hour, tzinfo=UTC),
        )
        for day, hour in ((1, 8), (2, 10), (3, 9))
    ]
    await make_notification(session, juans)

    first_page = await client.get("/notifications?limit=2", headers=bearer(ana))
    second_page = await client.get("/notifications?limit=2&offset=2", headers=bearer(ana))

    assert [n["id"] for n in first_page.json()] == [notices[1].id, notices[2].id]
    assert [n["id"] for n in second_page.json()] == [notices[0].id]


async def test_page_sizes_are_bounded(client, session):
    ana = await make_user(session)

    for query in ("limit=0", "limit=101", "offset=-1", "offset=100001"):
        response = await client.get(f"/notifications?{query}", headers=bearer(ana))
        assert response.status_code == 422, query
