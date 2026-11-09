import os

# Must be set before importing the app, which reads its settings on import.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://weather:weather@localhost:5432/weather_test",
)
os.environ["JWT_SECRET"] = "test-secret-at-least-32-bytes-long"

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


def joined_session(connection) -> AsyncSession:
    # Commits become savepoints inside the test's transaction, which is rolled back at the end.
    return AsyncSession(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


@pytest.fixture
async def connection():
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield connection
        await transaction.rollback()


@pytest.fixture
async def session(connection):
    """A session whose changes are rolled back after the test, even if the code commits."""
    async with joined_session(connection) as session:
        yield session


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
async def client(connection):
    # Each request gets its own session, as in production, on the test's transaction: it
    # sees what the test created, and a request that fails doesn't disturb the test's session.
    async def request_session():
        async with joined_session(connection) as request_session:
            yield request_session

    app.dependency_overrides[get_session] = request_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
