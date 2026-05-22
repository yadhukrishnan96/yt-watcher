import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import httpx

from .config import settings

logger = logging.getLogger(__name__)

YT_API_BASE = "https://www.googleapis.com/youtube/v3"

# In-memory cache: channel_id → uploadsPlaylistId
# Populated once at startup per channel, survives for the life of the process.
_uploads_playlist_cache: Dict[str, str] = {}


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
    try:
        from dateutil import parser as dtparser
        return dtparser.parse(raw)
    except Exception:
        return None


async def _resolve_uploads_playlist(channel_id: str, client: httpx.AsyncClient) -> Optional[str]:
    """
    Call channels.list to get the uploadsPlaylistId for a channel.
    Costs 1 quota unit. Result is cached in-process so this only runs once per channel.
    """
    if channel_id in _uploads_playlist_cache:
        return _uploads_playlist_cache[channel_id]

    try:
        resp = await client.get(
            f"{YT_API_BASE}/channels",
            params={
                "part": "contentDetails",
                "id": channel_id,
                "key": settings.youtube_api_key,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        logger.error(f"channels.list failed for {channel_id}: {exc}")
        return None

    items = data.get("items", [])
    if not items:
        logger.error(f"channels.list returned no items for channel_id={channel_id!r}. Check the ID is correct.")
        return None

    playlist_id = (
        items[0]
        .get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads")
    )

    if not playlist_id:
        logger.error(f"Could not extract uploadsPlaylistId for {channel_id}")
        return None

    logger.info(f"Resolved uploads playlist for {channel_id}: {playlist_id}")
    _uploads_playlist_cache[channel_id] = playlist_id
    return playlist_id


async def fetch_channel_videos(channel_id: str, client: httpx.AsyncClient) -> List[VideoEntry]:
    """
    Fetch the latest videos for a channel using playlistItems.list.
    Costs 1 quota unit per call (vs 100 for search.list).
    """
    playlist_id = await _resolve_uploads_playlist(channel_id, client)
    if not playlist_id:
        return []

    try:
        resp = await client.get(
            f"{YT_API_BASE}/playlistItems",
            params={
                "part": "snippet",
                "playlistId": playlist_id,
                "maxResults": 2,   # latest 10 — more than enough to catch new uploads
                "key": settings.youtube_api_key,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        # Surface quota errors clearly
        if exc.response.status_code == 403:
            logger.error(
                f"YouTube API 403 for channel {channel_id} — quota exceeded or API key invalid. "
                f"Response: {exc.response.text}"
            )
        else:
            logger.error(f"playlistItems.list HTTP {exc.response.status_code} for {channel_id}: {exc.response.text}")
        return []
    except httpx.RequestError as exc:
        logger.error(f"playlistItems.list request failed for {channel_id}: {exc}")
        return []

    items = data.get("items", [])
    videos: List[VideoEntry] = []

    for item in items:
        snippet = item.get("snippet", {})
        resource = snippet.get("resourceId", {})
        video_id = resource.get("videoId", "")

        if not video_id:
            continue

        # Deleted/private videos show up as "Private video" with no real ID
        title = snippet.get("title", "Untitled")
        if title in ("Private video", "Deleted video"):
            continue

        videos.append(
            VideoEntry(
                video_id=video_id,
                channel_id=channel_id,
                channel_name=snippet.get("channelTitle", channel_id),
                title=title,
                url=f"https://www.youtube.com/watch?v={video_id}",
                published_at=_parse_dt(snippet.get("publishedAt")),
            )
        )

    logger.info(
        f"Fetched {len(videos)} video(s) from channel "
        f"'{videos[0].channel_name if videos else channel_id}' ({channel_id})"
    )
    return videos
