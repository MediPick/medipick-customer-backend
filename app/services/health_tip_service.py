"""
MediPick — Health Tip Service
A11 public reads (published tips only) plus admin publishing.
"""
from __future__ import annotations

import math
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MediPickException
from app.core.timeutil import utcnow
from app.models.health_tip import HealthTip
from app.models.user import User
from app.schemas.health_tip import HealthTipCreateBody, HealthTipUpdateBody

_WORDS_PER_MINUTE = 200
_PREVIEW_CHARS = 160


def _read_time(body: str) -> int:
    return max(1, math.ceil(len(body.split()) / _WORDS_PER_MINUTE))


def _preview(body: str) -> str:
    text = " ".join(body.split())
    if len(text) <= _PREVIEW_CHARS:
        return text
    return text[:_PREVIEW_CHARS].rsplit(" ", 1)[0] + "…"


class HealthTipService:

    # ── A11.1 ─────────────────────────────────────────────────────────────────

    async def list_published(
        self, db: AsyncSession, category: str | None, page: int, limit: int
    ) -> tuple[list[HealthTip], int]:
        conditions = [HealthTip.is_published.is_(True)]
        if category:
            conditions.append(func.lower(HealthTip.category) == category.lower())
        total = (await db.execute(select(func.count()).select_from(HealthTip).where(*conditions))).scalar_one()
        result = await db.execute(
            select(HealthTip)
            .where(*conditions)
            .order_by(HealthTip.published_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    # ── A11.2 ─────────────────────────────────────────────────────────────────

    async def get_published(self, db: AsyncSession, tip_id: uuid.UUID) -> HealthTip:
        tip = (await db.execute(
            select(HealthTip).where(HealthTip.id == tip_id, HealthTip.is_published.is_(True))
        )).scalar_one_or_none()
        if tip is None:
            raise MediPickException("HEALTH_TIP_NOT_FOUND", 404, "Health tip not found.")
        return tip

    # ── Admin ────────────────────────────────────────────────────────────────

    async def create(self, db: AsyncSession, admin: User, body: HealthTipCreateBody) -> HealthTip:
        tip = HealthTip(
            admin_id=admin.id,
            title=body.title,
            category=body.category,
            content_body=body.bodyText,
            preview_text=body.previewText or _preview(body.bodyText),
            thumbnail_url=body.imageUrl,
            read_time_mins=_read_time(body.bodyText),
            is_published=body.isPublished,
            published_at=utcnow() if body.isPublished else None,
        )
        db.add(tip)
        await db.flush()
        return tip

    async def update(self, db: AsyncSession, tip_id: uuid.UUID, body: HealthTipUpdateBody) -> HealthTip:
        tip = (await db.execute(select(HealthTip).where(HealthTip.id == tip_id))).scalar_one_or_none()
        if tip is None:
            raise MediPickException("HEALTH_TIP_NOT_FOUND", 404, "Health tip not found.")

        if body.title is not None:
            tip.title = body.title
        if body.category is not None:
            tip.category = body.category
        if body.imageUrl is not None:
            tip.thumbnail_url = body.imageUrl
        if body.bodyText is not None:
            tip.content_body = body.bodyText
            tip.read_time_mins = _read_time(body.bodyText)
            if body.previewText is None:
                tip.preview_text = _preview(body.bodyText)
        if body.previewText is not None:
            tip.preview_text = body.previewText
        if body.isPublished is not None and body.isPublished != tip.is_published:
            tip.is_published = body.isPublished
            tip.published_at = utcnow() if body.isPublished else None

        await db.flush()
        return tip

    async def delete(self, db: AsyncSession, tip_id: uuid.UUID) -> None:
        tip = (await db.execute(select(HealthTip).where(HealthTip.id == tip_id))).scalar_one_or_none()
        if tip is None:
            raise MediPickException("HEALTH_TIP_NOT_FOUND", 404, "Health tip not found.")
        await db.delete(tip)
        await db.flush()


health_tip_service = HealthTipService()
