import pytest_asyncio

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models import Base


DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5432/ytwatcher_test"


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine(DATABASE_URL)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_factory() as session:
        yield session

    await engine.dispose()
