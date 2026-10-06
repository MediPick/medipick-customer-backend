"""
MediPick — Medicines Endpoints
A4.1 (list, public) / A4.2 (get, protected) + admin create/update/delete.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.exceptions import MediPickException
from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.medicine import (
    MedicineCreateBody,
    MedicineDeleteResponse,
    MedicineOut,
    MedicineUpdateBody,
)
from app.services.medicine_service import medicine_service

router = APIRouter(prefix="/medicines", tags=["Medicines"])


def _require_admin(user: User) -> None:
    if user.role != UserRole.PLATFORM_ADMIN:
        raise MediPickException("FORBIDDEN", 403, "This action requires platform admin privileges.")


@router.get("", response_model=PaginatedResponse[list[MedicineOut]], summary="A4.1 — List medicines")
async def list_medicines(
    search: str | None = Query(None),
    category: str | None = Query(None),
    pharmacyId: uuid.UUID | None = Query(None),
    isRxRequired: bool | None = Query(None),
    inStock: bool | None = Query(None),
    sort: str = Query("popularity"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Public catalogue listing with search/filter/sort/pagination."""
    rows, total = await medicine_service.list_medicines(
        db=db,
        search=search,
        category=category,
        pharmacy_id=pharmacyId,
        is_rx_required=isRxRequired,
        in_stock=inStock,
        sort=sort,
        page=page,
        limit=limit,
    )
    return PaginatedResponse(
        data=[
            MedicineOut.from_catalog_and_stock(m, category_name, price, stock, available_pharmacies)
            for m, category_name, price, stock, available_pharmacies in rows
        ],
        meta=PaginationMeta(
            page=page,
            limit=limit,
            total=total,
            totalPages=(total + limit - 1) // limit if limit else 0,
        ),
    )


@router.get("/{medicine_id}", response_model=SuccessResponse[MedicineOut], summary="A4.2 — Get medicine detail")
async def get_medicine(
    medicine_id: uuid.UUID,
    pharmacyId: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    medicine, category_name, price, stock, available_pharmacies = await medicine_service.get_medicine(db, medicine_id, pharmacyId)
    return SuccessResponse(data=MedicineOut.from_catalog_and_stock(medicine, category_name, price, stock, available_pharmacies))


@router.post(
    "", status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[MedicineOut], summary="Admin — Create medicine",
)
async def create_medicine(
    body: MedicineCreateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    medicine = await medicine_service.create_medicine(db, body)
    _, category_name, price, stock = await medicine_service.get_medicine(db, medicine.id)
    return SuccessResponse(data=MedicineOut.from_catalog_and_stock(medicine, category_name, price, stock))


@router.patch("/{medicine_id}", response_model=SuccessResponse[MedicineOut], summary="Admin — Update medicine")
async def update_medicine(
    medicine_id: uuid.UUID,
    body: MedicineUpdateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    medicine = await medicine_service.update_medicine(db, medicine_id, body)
    _, category_name, price, stock = await medicine_service.get_medicine(db, medicine.id)
    return SuccessResponse(data=MedicineOut.from_catalog_and_stock(medicine, category_name, price, stock))


@router.delete(
    "/{medicine_id}", response_model=SuccessResponse[MedicineDeleteResponse],
    summary="Admin — Delete medicine",
)
async def delete_medicine(
    medicine_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    await medicine_service.delete_medicine(db, medicine_id)
    return SuccessResponse(data=MedicineDeleteResponse())
