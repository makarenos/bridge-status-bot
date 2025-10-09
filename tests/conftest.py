"""
Pytest fixtures and test configuration
All the shared test setup lives here
"""

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.models.bridge import Bridge, BridgeStatus, Incident
from app.models.user import User, UserSubscription


# test database URL - using in-memory SQLite for speed
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """
    Create event loop for async tests
    Session-scoped so we can reuse it
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    """
    Create test database engine
    Each test gets fresh DB
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )

    # create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create test database session
    Auto-rollback after each test
    """
    async_session = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def sample_bridge(db_session: AsyncSession) -> Bridge:
    """
    Create sample bridge for testing
    """
    bridge = Bridge(
        name="Test Bridge",
        api_endpoint="https://test.bridge.io/api/status",
        backup_endpoint=None,
        is_active=True,
        check_interval_seconds=300,
    )
    db_session.add(bridge)
    await db_session.commit()
    await db_session.refresh(bridge)
    return bridge


@pytest_asyncio.fixture
async def sample_bridges(db_session: AsyncSession) -> list[Bridge]:
    """
    Create multiple bridges for testing
    """
    bridges = [
        Bridge(
            name="Stargate",
            api_endpoint="https://api.stargate.finance/v1/status",
            is_active=True,
        ),
        Bridge(
            name="Hop Protocol",
            api_endpoint="https://hop.exchange/v1-1/available-liquidity",
            is_active=True,
        ),
        Bridge(
            name="Arbitrum Bridge",
            api_endpoint="https://bridge.arbitrum.io/api/status",
            is_active=False,  # one inactive for testing
        ),
    ]

    for bridge in bridges:
        db_session.add(bridge)

    await db_session.commit()

    for bridge in bridges:
        await db_session.refresh(bridge)

    return bridges


@pytest_asyncio.fixture
async def sample_user(db_session: AsyncSession) -> User:
    """
    Create sample user for testing
    """
    user = User(
        telegram_id=123456789,
        username="test_user",
        notifications_enabled=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def sample_subscription(
    db_session: AsyncSession,
    sample_user: User,
    sample_bridge: Bridge
) -> UserSubscription:
    """
    Create sample subscription for testing
    """
    sub = UserSubscription(
        user_id=sample_user.telegram_id,
        bridge_id=sample_bridge.id,
        alert_on_down=True,
        alert_on_slow=False,
        alert_on_warning=True,
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


@pytest_asyncio.fixture
async def sample_status(
    db_session: AsyncSession,
    sample_bridge: Bridge
) -> BridgeStatus:
    """
    Create sample bridge status for testing
    """
    status = BridgeStatus(
        bridge_id=sample_bridge.id,
        status="UP",
        response_time=2500,
        error_message=None,
        extra_data={'test': True},
        checked_at=datetime.now(timezone.utc),
    )
    db_session.add(status)
    await db_session.commit()
    await db_session.refresh(status)
    return status


@pytest_asyncio.fixture
async def sample_incident(
    db_session: AsyncSession,
    sample_bridge: Bridge
) -> Incident:
    """
    Create sample incident for testing
    """
    incident = Incident(
        bridge_id=sample_bridge.id,
        title="Test Bridge is DOWN",
        description="Test incident",
        status="ACTIVE",
        severity="HIGH",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(incident)
    await db_session.commit()
    await db_session.refresh(incident)
    return incident


@pytest.fixture
def mock_redis_client():
    """
    Mock Redis client for testing
    Stores data in dict instead of real Redis
    """
    class MockRedis:
        def __init__(self):
            self.data = {}
            self.redis = self

        async def connect(self):
            pass

        async def close(self):
            pass

        async def get(self, key: str):
            return self.data.get(key)

        async def set(self, key: str, value, ex=None):
            self.data[key] = value
            return True

        async def delete(self, key: str):
            if key in self.data:
                del self.data[key]
                return True
            return False

        async def exists(self, key: str):
            return key in self.data

        async def setex(self, key: str, seconds: int, value):
            return await self.set(key, value, ex=seconds)

        async def incr(self, key: str):
            current = int(self.data.get(key, 0))
            self.data[key] = str(current + 1)
            return current + 1

        async def expire(self, key: str, seconds: int):
            return True

        async def ping(self):
            return True

    return MockRedis()


@pytest.fixture
def mock_http_response():
    """
    Mock HTTP response for testing bridge checks
    """
    class MockResponse:
        def __init__(self, status=200, json_data=None):
            self.status = status
            self._json_data = json_data or {}

        async def json(self):
            return self._json_data

        async def read(self):
            return b"mock response"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    return MockResponse