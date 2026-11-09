import os

# Must be set before importing the app, which reads its settings on import.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://weather:weather@localhost:5432/weather_test",
)

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import get_session
from app.main import app
from app.models import Base

# NullPool: each test runs on its own event loop, so pooled connections can't be reused.
engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)


@pytest.fixture(scope="session")
def alembic_config():
    return Config("alembic.ini")


@pytest.fixture(scope="session", autouse=True)
def migrated_database(alembic_config):
    command.upgrade(alembic_config, "head")


@pytest.fixture
async def session():
    """A session whose changes are rolled back after the test, even if the code commits."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        yield session
        await session.close()
        await transaction.rollback()


@pytest.fixture
async def committed_sessions():
    """Sessions that really commit, for tests that need several connections at once.

    Everything is truncated afterwards, so keep these tests few.
    """
    yield async_sessionmaker(engine, expire_on_commit=False)
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def client(session):
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
