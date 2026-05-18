import asyncio
import logging
from datetime import datetime

import httpx
from sqlalchemy import select

from .config import settings
from .feed import VideoEntry, fetch_channel_videos
from .models import SeenVideo
from .notifier import send_telegram_notification

logger = logging.getLogger(__name__)

REDIS_KEY_PREFIX = "yt:seen:"
REDIS_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


async def _is_seen_redis(redis, video_id: str) -> bool:
    return await redis.exists(f"{REDIS_KEY_PREFIX}{video_id}") == 1


async def _mark_seen_redis(redis, video_id: str):
    await redis.set(
        f"{REDIS_KEY_PREFIX}{video_id}",
        "1",
        ex=REDIS_TTL_SECONDS,
    )


async def _is_seen_db(session, video_id: str) -> bool:
    result = await session.execute(
        select(SeenVideo).where(SeenVideo.video_id == video_id)
    )
    return result.scalar_one_or_none() is not None


async def _mark_seen_db(session, video: VideoEntry):
    row = SeenVideo(
        video_id=video.video_id,
        channel_id=video.channel_id,
        channel_name=video.channel_name,
        title=video.title,
        url=video.url,
        published_at=video.published_at,
        notified_at=datetime.utcnow(),
    )

    session.add(row)
    await session.commit()


async def poll_once(app):
    redis = app.state.redis
    async_session = app.state.async_session

    async with httpx.AsyncClient() as client:
        for channel_id in settings.youtube_channel_ids:
            videos = await fetch_channel_videos(channel_id, client)

            for video in videos:
                if not video.video_id:
                    continue

                # Fast path: Redis cache
                if await _is_seen_redis(redis, video.video_id):
                    continue

                # Slow path: DB check (handles Redis eviction / restarts)
                async with async_session() as session:
                    if await _is_seen_db(session, video.video_id):
                        # Backfill Redis so next check is fast
                        await _mark_seen_redis(redis, video.video_id)
                        continue

                    # New video — notify and persist
                    logger.info(
                        f"New video detected: "
                        f"[{video.channel_name}] {video.title} ({video.video_id})"
                    )

                    notified = await send_telegram_notification(video)

                    await _mark_seen_db(session, video)
                    await _mark_seen_redis(redis, video.video_id)

                    if notified:
                        logger.info(f"Notification sent for {video.video_id}")
                    else:
                        logger.warning(
                            f"Notification FAILED for {video.video_id} "
                            f"— still marked seen to avoid spam"
                        )


async def start_poller(app):
    while True:
        try:
            await poll_once(app)
        except Exception:
            logger.exception("Poller loop failed")

        await asyncio.sleep(settings.poll_interval_seconds)
