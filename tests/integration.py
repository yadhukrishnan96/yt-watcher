from datetime import datetime, timezone

import pytest

from app.feed import VideoEntry
from app.poller import _is_seen_db, _mark_seen_db


@pytest.mark.asyncio
async def test_video_seen(async_session):
    video = VideoEntry(
        video_id="abc123",
        channel_id="channel123",
        channel_name="Test Channel",
        title="Test Video",
        url="https://youtube.com/watch?v=abc123",
        published_at=datetime.now(timezone.utc),
    )

    # Should not exist initially
    seen_before = await _is_seen_db(
        async_session,
        video.video_id,
    )

    assert seen_before is False

    # Store in DB using real app code
    await _mark_seen_db(
        async_session,
        video,
    )

    # Should now exist
    seen_after = await _is_seen_db(
        async_session,
        video.video_id,
    )

    assert seen_after is True
