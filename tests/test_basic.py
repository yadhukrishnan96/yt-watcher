from unittest.mock import AsyncMock

import pytest

from app.poller import (
    _mark_seen_redis,
    REDIS_KEY_PREFIX,
    REDIS_TTL_SECONDS,
)


@pytest.mark.asyncio
async def test_mark_seen_redis():
    # Fake Redis client
    redis = AsyncMock()

    # Run the function
    await _mark_seen_redis(redis, "abc123")

    # Verify Redis received the correct command
    redis.set.assert_called_once_with(
        f"{REDIS_KEY_PREFIX}abc123",
        "1",
        ex=REDIS_TTL_SECONDS,
    )
