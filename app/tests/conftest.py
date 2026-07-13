import asyncio
import pytest
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from httpx import AsyncClient

from app.main import app
from app.database import Base, get_db

# Isolated SQLite test database
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_analytics.db"

test_engine = create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

@pytest.fixture(scope="session")
def event_loop():
    """
    Fixture to define the event loop for asynchronous operations.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session", autouse=True)
async def init_db():
    """
    Session-wide schema creation and teardown.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provides a transactional database session per test.
    """
    async with TestSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

@pytest.fixture(autouse=True)
def override_db(db_session):
    """
    Overrides the production DB dependency with the test database.
    """
    async def _get_test_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_test_db
    yield
    app.dependency_overrides.clear()

@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Provides an async HTTP test client.
    """
    async with AsyncClient(app=app, base_url="http://testserver") as ac:
        yield ac
