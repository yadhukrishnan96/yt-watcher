import logging

import httpx

from .config import settings
from .feed import VideoEntry

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _format_message(video: VideoEntry) -> str:
    pub = (
        video.published_at.strftime("%Y-%m-%d %H:%M UTC")
        if video.published_at
        else "Unknown time"
    )
    return (
        f"🎬 New video from {video.channel_name}\n\n"
        f"📌 Title: {video.title}\n"
        f"🕒 Published: {pub}\n"
        f"🔗 {video.url}"
    )


async def send_telegram_notification(video: VideoEntry) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram credentials not configured — skipping notification")
        return False

    url = TELEGRAM_API.format(token=settings.telegram_bot_token)
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": _format_message(video),
        "disable_web_page_preview": False,
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=10.0)
            resp.raise_for_status()
            logger.info(f"Telegram notification sent for video: {video.video_id}")
            return True
        except httpx.HTTPStatusError as exc:
            logger.error(
                f"Telegram API error {exc.response.status_code}: {exc.response.text}"
            )
        except httpx.RequestError as exc:
            logger.error(f"Telegram request failed: {exc}")
    return False
