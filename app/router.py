import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, desc

from .config import settings
from .models import SeenVideo
from .poller import poll_once

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["watcher"])


# ── Pydantic schemas ────────────────────────────────────────────────────────

class VideoOut(BaseModel):
    video_id: str
    channel_id: str
    channel_name: Optional[str]
    title: str
    url: str
    published_at: Optional[str]
    notified_at: str

    class Config:
        from_attributes = True


class StatusOut(BaseModel):
    poll_interval_seconds: int
    tracked_channels: List[str]
    telegram_configured: bool


# ── Helpers ─────────────────────────────────────────────────────────────────

def get_session(request: Request):
    return request.app.state.async_session()


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/status", response_model=StatusOut)
async def status():
    """Returns runtime configuration — useful for verifying env vars without restarting."""
    return StatusOut(
        poll_interval_seconds=settings.poll_interval_seconds,
        tracked_channels=settings.youtube_channel_ids,
        telegram_configured=bool(settings.telegram_bot_token and settings.telegram_chat_id),
    )


@router.get("/videos", response_model=List[VideoOut])
async def list_seen_videos(
    request: Request,
    channel_id: Optional[str] = None,
    limit: int = 50,
):
    """List all videos we have already seen and notified about."""
    async with request.app.state.async_session() as session:
        q = select(SeenVideo).order_by(desc(SeenVideo.notified_at)).limit(limit)
        if channel_id:
            q = q.where(SeenVideo.channel_id == channel_id)
        result = await session.execute(q)
        rows = result.scalars().all()

    return [
        VideoOut(
            video_id=r.video_id,
            channel_id=r.channel_id,
            channel_name=r.channel_name,
            title=r.title,
            url=r.url,
            published_at=r.published_at.isoformat() if r.published_at else None,
            notified_at=r.notified_at.isoformat(),
        )
        for r in rows
    ]


@router.post("/poll", status_code=202)
async def trigger_poll(request: Request):
    """
    Manually trigger a poll cycle immediately.
    Useful for testing or forcing a check without waiting for the interval.
    """
    import asyncio
    asyncio.create_task(poll_once(request.app))
    return {"message": "Poll cycle triggered asynchronously"}


@router.delete("/videos/{video_id}", status_code=200)
async def forget_video(video_id: str, request: Request):
    """
    Remove a video from the seen list (Redis + DB).
    The next poll will re-detect it and re-notify.
    Useful for testing notifications.
    """
    redis = request.app.state.redis
    async with request.app.state.async_session() as session:
        result = await session.execute(
            select(SeenVideo).where(SeenVideo.video_id == video_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail=f"Video {video_id!r} not in seen list")
        await session.delete(row)
        await session.commit()

    await redis.delete(f"yt:seen:{video_id}")
    return {"message": f"Video {video_id!r} removed from seen list"}
