import logging
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass

import httpx
import xmltodict

from .config import settings

logger = logging.getLogger(__name__)


@dataclass
class VideoEntry:
    video_id: str
    channel_id: str
    channel_name: str
    title: str
    url: str
    published_at: Optional[datetime]


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(raw[:25], fmt[: len(raw[:25])])
        except ValueError:
            continue
    try:
        from dateutil import parser as dtparser

        return dtparser.parse(raw)
    except Exception:
        return None


async def fetch_channel_videos(
    channel_id: str, client: httpx.AsyncClient
) -> List[VideoEntry]:
    url = f"{settings.youtube_rss_base}{channel_id}"
    try:
        resp = await client.get(url, timeout=15.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error(f"Failed to fetch RSS for channel {channel_id}: {exc}")
        return []

    try:
        data = xmltodict.parse(resp.text)
    except Exception as exc:
        logger.error(f"Failed to parse RSS XML for channel {channel_id}: {exc}")
        return []

    feed = data.get("feed", {})
    channel_name = feed.get("title", channel_id)
    raw_entries = feed.get("entry", [])

    # xmltodict returns a dict (not list) when there's only one entry
    if isinstance(raw_entries, dict):
        raw_entries = [raw_entries]

    videos: List[VideoEntry] = []
    for entry in raw_entries:
        yt_ns = entry.get("yt:videoId") or entry.get("videoId", "")
        link_data = entry.get("link", {})
        if isinstance(link_data, list):
            link_data = link_data[0]
        link = link_data.get("@href", "") if isinstance(link_data, dict) else ""

        videos.append(
            VideoEntry(
                video_id=yt_ns,
                channel_id=channel_id,
                channel_name=channel_name,
                title=entry.get("title", "Untitled"),
                url=link or f"https://www.youtube.com/watch?v={yt_ns}",
                published_at=_parse_dt(entry.get("published")),
            )
        )

    logger.info(
        f"Fetched {len(videos)} video(s) from channel '{channel_name}' ({channel_id})"
    )
    return videos
