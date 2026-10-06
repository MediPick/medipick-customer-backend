"""
MediPick — Health Tip Pydantic Schemas
Field names match src/api/healthTipsApi.ts.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.health_tip import HealthTip


class HealthTipOut(BaseModel):
    id: str
    title: str
    category: str
    previewText: str
    bodyText: str
    imageUrl: str | None
    publishedAt: datetime | None
    readTimeMins: int

    @staticmethod
    def from_tip(t: HealthTip) -> "HealthTipOut":
        return HealthTipOut(
            id=str(t.id),
            title=t.title,
            category=t.category,
            previewText=t.preview_text,
            bodyText=t.content_body,
            imageUrl=t.thumbnail_url,
            publishedAt=t.published_at,
            readTimeMins=t.read_time_mins,
        )


class HealthTipCreateBody(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    category: str = Field(..., min_length=2, max_length=100)
    bodyText: str = Field(..., min_length=10)
    previewText: str | None = Field(None, max_length=300)
    imageUrl: str | None = None
    isPublished: bool = True


class HealthTipUpdateBody(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=255)
    category: str | None = Field(None, min_length=2, max_length=100)
    bodyText: str | None = Field(None, min_length=10)
    previewText: str | None = Field(None, max_length=300)
    imageUrl: str | None = None
    isPublished: bool | None = None
