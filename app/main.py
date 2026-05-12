import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from .config import settings
from .models import Base
from .poller import start_poller
from .router import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== YouTube RSS Watcher starting up ===")
    logger.info(f"Effective poll interval : {settings.poll_interval_seconds}s")
    logger.info(f"Tracking {len(settings.youtube_channel_ids)} channel(s): {settings.youtube_channel_ids}")

    # ── Postgres ─────────────────────────────────────────────────────────────
    app.state.engine = create_async_engine(settings.database_url, echo=False)
    async with app.state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.state.async_session = sessionmaker(
        app.state.engine, class_=AsyncSession, expire_on_commit=False
    )
    logger.info("PostgreSQL connection OK — tables ready")

    # ── Redis ─────────────────────────────────────────────────────────────────
    app.state.redis = aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )
    await app.state.redis.ping()
    logger.info("Redis connection OK")

    # ── Background poller ────────────────────────────────────────────────────
    poller_task = asyncio.create_task(start_poller(app))
    logger.info(f"Background poller started — first run in {settings.poll_interval_seconds}s")

    yield

    # ── Graceful shutdown ────────────────────────────────────────────────────
    logger.info("Shutting down gracefully...")
    poller_task.cancel()
    try:
        await poller_task
    except asyncio.CancelledError:
        pass
    await app.state.redis.aclose()
    await app.state.engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="YouTube RSS Watcher",
    description=(
        "Polls YouTube RSS feeds on a configurable interval and sends "
        "Telegram notifications when tracked channels publish new videos."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)


leak = []

@app.get("/oom")
def trigger_oom():
    for _ in range(50):
        leak.append("x" * 2_000_000)
    return {"status": "allocating memory", "size": len(leak)}


@app.get("/oom")
def trigger_oom():
    for _ in range(50):
        leak.append("x" * 2_000_000)
    return {"status": "allocating memory", "size": len(leak)}





@app.get("/healthz", tags=["ops"])
async def health():
    """Kubernetes liveness / readiness probe endpoint."""
    return {"status": "ok"}



@app.get("/readyz", tags=["ops"])
async def ready(request: Request):
    """Kubernetes readiness probe endpoint."""
    try:
        # PostgreSQL check
        async with request.app.state.async_session() as session:
            await session.execute(text("SELECT 1"))

        # Redis check
        await request.app.state.redis.ping()

        return {"status": "ready"}

    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


