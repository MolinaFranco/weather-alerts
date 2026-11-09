from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db import get_session
from app.main import app


async def test_health_ok(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_returns_503_when_the_database_is_unreachable():
    unreachable = create_async_engine("postgresql+asyncpg://weather:weather@localhost:1/weather")

    async def unreachable_session():
        async with AsyncSession(unreachable) as session:
            yield session

    app.dependency_overrides[get_session] = unreachable_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
    finally:
        app.dependency_overrides.clear()
        await unreachable.dispose()

    assert response.status_code == 503
