"""
MediPick — Pharmacies Endpoints
A3.1 (list, public) / A3.2 (get, public) / A3.3-A3.5 (favorites, protected).
A3.1/A3.2 personalize isFavorite/favoriteId when a valid Bearer token is present,
but don't require one.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_customer_user, get_optional_current_customer
from app.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.pharmacy import AddFavoriteResponse, PharmacyOut
from app.services.pharmacy_service import pharmacy_service

router = APIRouter(prefix="/pharmacies", tags=["Pharmacies"])


@router.get("", response_model=PaginatedResponse[list[PharmacyOut]], summary="A3.1 — List pharmacies")
async def list_pharmacies(
    search: str | None = Query(None),
    latitude: float | None = Query(None),
    longitude: float | None = Query(None),
    sort: str = Query("distance"),
    isOpen: bool | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_customer: tuple[User, Customer] | None = Depends(get_optional_current_customer),
):
    """Public listing with search, GPS distance sort, and open/closed filter."""
    customer_id = current_customer[1].id if current_customer else None
    rows, total = await pharmacy_service.list_pharmacies(
        db=db,
        search=search,
        latitude=latitude,
        longitude=longitude,
        sort=sort,
        is_open=isOpen,
        page=page,
        limit=limit,
        customer_id=customer_id,
    )
    return PaginatedResponse(
        data=[
            PharmacyOut.from_pharmacy(p, distance, is_favorite, favorite_id)
            for p, distance, is_favorite, favorite_id in rows
        ],
        meta=PaginationMeta(
            page=page, limit=limit, total=total,
            totalPages=(total + limit - 1) // limit if limit else 0,
        ),
    )


@router.get("/favorites", response_model=SuccessResponse[list[PharmacyOut]], summary="A3.3 — List favorite pharmacies")
async def list_favorite_pharmacies(
    latitude: float | None = Query(None),
    longitude: float | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_customer: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current_customer
    rows = await pharmacy_service.list_favorite_pharmacies(db, customer.id, latitude, longitude)
    return SuccessResponse(
        data=[PharmacyOut.from_pharmacy(p, distance, is_fav, fav_id) for p, distance, is_fav, fav_id in rows]
    )


@router.get("/{pharmacy_id}", response_model=SuccessResponse[PharmacyOut], summary="A3.2 — Get pharmacy detail")
async def get_pharmacy(
    pharmacy_id: uuid.UUID,
    latitude: float | None = Query(None),
    longitude: float | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_customer: tuple[User, Customer] | None = Depends(get_optional_current_customer),
):
    customer_id = current_customer[1].id if current_customer else None
    pharmacy, distance, is_favorite, favorite_id = await pharmacy_service.get_pharmacy(
        db, pharmacy_id, latitude, longitude, customer_id
    )
    return SuccessResponse(data=PharmacyOut.from_pharmacy(pharmacy, distance, is_favorite, favorite_id))


@router.post(
    "/{pharmacy_id}/favorites", status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[AddFavoriteResponse], summary="A3.4 — Add pharmacy to favorites",
)
async def add_favorite(
    pharmacy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_customer: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current_customer
    favorite = await pharmacy_service.add_favorite(db, customer.id, pharmacy_id)
    return SuccessResponse(
        data=AddFavoriteResponse(favoriteId=str(favorite.id), pharmacyId=str(pharmacy_id))
    )


@router.delete(
    "/{pharmacy_id}/favorites/{favorite_id}",
    response_model=SuccessResponse[dict], summary="A3.5 — Remove pharmacy from favorites",
)
async def remove_favorite(
    pharmacy_id: uuid.UUID,
    favorite_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_customer: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current_customer
    await pharmacy_service.remove_favorite(db, customer.id, pharmacy_id, favorite_id)
    return SuccessResponse(data={})
