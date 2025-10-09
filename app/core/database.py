"""
PostgreSQL connection setup with async SQLAlchemy
DB engine and session factory live here
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings
from app.utils.logger import logger


# base class for all models
class Base(DeclarativeBase):
    """Base class for SQLAlchemy models"""
    pass


# fix Render's database URL for async driver
database_url = settings.database_url.replace(
    "postgresql://",
    "postgresql+asyncpg://"
)

# create async engine for DB work
engine = create_async_engine(
    database_url,
    echo=settings.debug,  # show SQL queries in debug mode
    pool_pre_ping=True,  # check connection before using it
    pool_size=10,  # connection pool size
    max_overflow=20,  # max extra connections
)

# factory for creating sessions
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # don't reset objects after commit
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI endpoints

    Usage:
        @app.get("/something")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            # do something with db
    """
    async with async_session_maker() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables (dev only!)"""
    # in production use Alembic migrations
    logger.warning("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created!")


async def close_db():
    """Close all DB connections on shutdown"""
    logger.info("Closing database connections...")
    await engine.dispose()
    logger.info("Database connections closed")