"""MediPick — time helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import settings

LOCAL_TZ = timezone(timedelta(minutes=settings.APP_UTC_OFFSET_MINUTES))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_aware(dt: datetime) -> datetime:
    """DB drivers can hand back naive datetimes; treat those as UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def format_local_clock(dt: datetime) -> str:
    """e.g. "2:15 PM" in the app's local timezone (Sri Lanka by default)."""
    return as_aware(dt).astimezone(LOCAL_TZ).strftime("%I:%M %p").lstrip("0")
