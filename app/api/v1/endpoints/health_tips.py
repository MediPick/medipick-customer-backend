"""
MediPick — Health Tips Endpoints
A11.1 / A11.2 are public. Writes are PLATFORM_ADMIN only.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.common import MessageResponse, PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.health_tip import HealthTipCreateBody, HealthTipOut, HealthTipUpdateBody
from app.services.health_tip_service import health_tip_service

router = APIRouter(prefix="/health-tips", tags=["Health Tips"])

_admin = require_roles(UserRole.PLATFORM_ADMIN)


@router.get("", response_model=PaginatedResponse[list[HealthTipOut]], summary="A11.1 — List health tips")
async def list_health_tips(
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    tips, total = await health_tip_service.list_published(db, category, page, limit)
    return PaginatedResponse(data=[HealthTipOut.from_tip(t) for t in tips], meta=PaginationMeta.build(page, limit, total))


@router.get("/{tip_id}", response_model=SuccessResponse[HealthTipOut], summary="A11.2 — Health tip detail")
async def get_health_tip(tip_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return SuccessResponse(data=HealthTipOut.from_tip(await health_tip_service.get_published(db, tip_id)))


@router.post(
    "", status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[HealthTipOut], summary="Admin — Publish a health tip",
)
async def create_health_tip(
    body: HealthTipCreateBody,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_admin),
):
    return SuccessResponse(data=HealthTipOut.from_tip(await health_tip_service.create(db, admin, body)))


@router.patch("/{tip_id}", response_model=SuccessResponse[HealthTipOut], summary="Admin — Update a health tip")
async def update_health_tip(
    tip_id: uuid.UUID,
    body: HealthTipUpdateBody,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_admin),
):
    return SuccessResponse(data=HealthTipOut.from_tip(await health_tip_service.update(db, tip_id, body)))


@router.delete("/{tip_id}", response_model=SuccessResponse[MessageResponse], summary="Admin — Delete a health tip")
async def delete_health_tip(
    tip_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_admin),
):
    await health_tip_service.delete(db, tip_id)
    return SuccessResponse(data=MessageResponse(message="Health tip deleted."))
