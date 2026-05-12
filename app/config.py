import logging
import os
from typing import List

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 900  # 15 minutes


def _parse_poll_interval() -> int:
    raw = os.getenv("POLL_INTERVAL_SECONDS", "")
    if raw.strip():
        try:
            val = int(raw.strip())
            if val > 0:
                return val
            logger.warning(
                f"POLL_INTERVAL_SECONDS must be > 0, got {val!r}. Falling back to {DEFAULT_POLL_INTERVAL}s."
            )
        except ValueError:
            logger.warning(
                f"POLL_INTERVAL_SECONDS is not a valid integer: {raw!r}. Falling back to {DEFAULT_POLL_INTERVAL}s."
            )
    else:
        logger.info(
            f"POLL_INTERVAL_SECONDS not set. Using default: {DEFAULT_POLL_INTERVAL}s."
        )
    return DEFAULT_POLL_INTERVAL


def _parse_channel_ids() -> List[str]:
    raw = os.getenv("YOUTUBE_CHANNEL_IDS", "")
    ids = [cid.strip() for cid in raw.split(",") if cid.strip()]
    if not ids:
        raise ValueError(
            "YOUTUBE_CHANNEL_IDS env var is required. Provide comma-separated YouTube channel IDs."
        )
    return ids


class Settings:
    poll_interval_seconds: int = _parse_poll_interval()
    youtube_channel_ids: List[str] = _parse_channel_ids()
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/ytwatcher"
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    youtube_rss_base: str = "https://www.youtube.com/feeds/videos.xml?channel_id="

    def validate(self):
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN env var is required.")
        if not self.telegram_chat_id:
            raise ValueError("TELEGRAM_CHAT_ID env var is required.")


settings = Settings()
