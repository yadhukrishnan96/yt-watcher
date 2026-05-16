from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SeenVideo(Base):
    """Tracks videos we have already notified about, keyed by video ID."""

    __tablename__ = "seen_videos"

    video_id = Column(String(64), primary_key=True, index=True)
    channel_id = Column(String(64), nullable=False, index=True)
    channel_name = Column(String(256), nullable=True)
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    notified_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
