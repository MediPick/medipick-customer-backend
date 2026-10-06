"""
MediPick — Notifications Endpoints (A10.1 → A10.3)
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.notification import MarkAllReadResponse, MarkReadBody, MarkReadResponse, NotificationOut
from app.services.notification_service import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=PaginatedResponse[list[NotificationOut]], summary="A10.1 — List notifications")
async def list_notifications(
    unreadOnly: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """With unreadOnly=true&limit=1, `meta.total` is the unread badge count."""
    items, total = await notification_service.list_notifications(db, user.id, unreadOnly, page, limit)
    return PaginatedResponse(
        data=[NotificationOut.from_notification(n) for n in items],
        meta=PaginationMeta.build(page, limit, total),
    )


@router.post("/read-all", response_model=SuccessResponse[MarkAllReadResponse], summary="A10.3 — Mark all read")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    marked = await notification_service.mark_all_read(db, user.id)
    return SuccessResponse(data=MarkAllReadResponse(markedCount=marked))


@router.patch("/{notification_id}", response_model=SuccessResponse[MarkReadResponse], summary="A10.2 — Mark one read")
async def mark_read(
    notification_id: uuid.UUID,
    body: MarkReadBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    n = await notification_service.set_read(db, user.id, notification_id, body.read)
    return SuccessResponse(data=MarkReadResponse(id=str(n.id), read=n.is_read))
