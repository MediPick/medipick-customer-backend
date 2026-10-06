"""
MediPick — Pharmacy Service
Business logic for the Pharmacies domain: public listing/detail (A3.1, A3.2)
and customer favorites (A3.3, A3.4, A3.5).
"""
from __future__ import annotations

import math
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MediPickException
from app.models.favorite_pharmacy import FavoritePharmacy
from app.models.pharmacy import Pharmacy


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometers between two lat/long points."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _format_distance(
    pharmacy: Pharmacy, latitude: float | None, longitude: float | None
) -> tuple[str, float | None]:
    """Returns (display string, raw km for sorting). Falls back to "-" when either
    the customer's or the pharmacy's coordinates are unknown."""
    if latitude is None or longitude is None or pharmacy.latitude is None or pharmacy.longitude is None:
        return "-", None
    km = _haversine_km(latitude, longitude, float(pharmacy.latitude), float(pharmacy.longitude))
    return f"{km:.1f} km", km


class PharmacyService:

    # ── List (A3.1) ───────────────────────────────────────────────────────────

    async def list_pharmacies(
        self,
        db: AsyncSession,
        search: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        sort: str = "distance",
        is_open: bool | None = None,
        page: int = 1,
        limit: int = 20,
        customer_id: uuid.UUID | None = None,
    ) -> tuple[list[tuple[Pharmacy, str, bool | None, str | None]], int]:
        query = select(Pharmacy)
        count_query = select(func.count()).select_from(Pharmacy)

        if search:
            like = f"%{search}%"
            cond = Pharmacy.name.ilike(like) | Pharmacy.address.ilike(like)
            query = query.where(cond)
            count_query = count_query.where(cond)
        if is_open is not None:
            query = query.where(Pharmacy.is_open == is_open)
            count_query = count_query.where(Pharmacy.is_open == is_open)

        total = (await db.execute(count_query)).scalar_one()

        if sort == "rating":
            query = query.order_by(
                (Pharmacy.rating_total / func.nullif(Pharmacy.rating_count, 0)).desc().nullslast()
            )
        elif sort == "popularity":
            # No dedicated popularity metric yet — rating_count is the closest proxy.
            query = query.order_by(Pharmacy.rating_count.desc())
        # "distance" (default) is resolved in Python below since it needs Haversine.

        result = await db.execute(query)
        pharmacies = list(result.scalars().all())

        favorite_ids: set[uuid.UUID] = set()
        favorite_id_map: dict[uuid.UUID, uuid.UUID] = {}
        if customer_id is not None and pharmacies:
            fav_result = await db.execute(
                select(FavoritePharmacy).where(
                    FavoritePharmacy.customer_id == customer_id,
                    FavoritePharmacy.pharmacy_id.in_([p.id for p in pharmacies]),
                )
            )
            for fav in fav_result.scalars().all():
                favorite_ids.add(fav.pharmacy_id)
                favorite_id_map[fav.pharmacy_id] = fav.id

        rows: list[tuple[Pharmacy, str, bool | None, str | None, float | None]] = []
        for p in pharmacies:
            distance_str, distance_km = _format_distance(p, latitude, longitude)
            is_favorite = (p.id in favorite_ids) if customer_id is not None else None
            favorite_id = str(favorite_id_map[p.id]) if p.id in favorite_id_map else None
            rows.append((p, distance_str, is_favorite, favorite_id, distance_km))

        if sort == "distance":
            rows.sort(key=lambda r: (r[4] is None, r[4]))

        start = (page - 1) * limit
        page_rows = rows[start: start + limit]
        return [(p, d, fav, fid) for p, d, fav, fid, _ in page_rows], total

    # ── Get Single (A3.2) ────────────────────────────────────────────────────

    async def get_pharmacy(
        self,
        db: AsyncSession,
        pharmacy_id: uuid.UUID,
        latitude: float | None = None,
        longitude: float | None = None,
        customer_id: uuid.UUID | None = None,
    ) -> tuple[Pharmacy, str, bool | None, str | None]:
        result = await db.execute(select(Pharmacy).where(Pharmacy.id == pharmacy_id))
        pharmacy = result.scalar_one_or_none()
        if pharmacy is None:
            raise MediPickException("PHARMACY_NOT_FOUND", 404, "Pharmacy not found.")

        distance_str, _ = _format_distance(pharmacy, latitude, longitude)

        is_favorite = None
        favorite_id = None
        if customer_id is not None:
            fav_result = await db.execute(
                select(FavoritePharmacy).where(
                    FavoritePharmacy.customer_id == customer_id,
                    FavoritePharmacy.pharmacy_id == pharmacy_id,
                )
            )
            fav = fav_result.scalar_one_or_none()
            is_favorite = fav is not None
            favorite_id = str(fav.id) if fav else None

        return pharmacy, distance_str, is_favorite, favorite_id

    # ── List Favorites (A3.3) ─────────────────────────────────────────────────

    async def list_favorite_pharmacies(
        self, db: AsyncSession, customer_id: uuid.UUID,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> list[tuple[Pharmacy, str, bool, str]]:
        result = await db.execute(
            select(Pharmacy, FavoritePharmacy.id)
            .join(FavoritePharmacy, FavoritePharmacy.pharmacy_id == Pharmacy.id)
            .where(FavoritePharmacy.customer_id == customer_id)
        )
        
        rows = []
        for p, fav_id in result.all():
            distance_str, _ = _format_distance(p, latitude, longitude)
            rows.append((p, distance_str, True, str(fav_id)))
            
        return rows

    # ── Add Favorite (A3.4) ───────────────────────────────────────────────────

    async def add_favorite(
        self, db: AsyncSession, customer_id: uuid.UUID, pharmacy_id: uuid.UUID
    ) -> FavoritePharmacy:
        pharmacy_result = await db.execute(select(Pharmacy).where(Pharmacy.id == pharmacy_id))
        if pharmacy_result.scalar_one_or_none() is None:
            raise MediPickException("PHARMACY_NOT_FOUND", 404, "Pharmacy not found.")

        existing = await db.execute(
            select(FavoritePharmacy).where(
                FavoritePharmacy.customer_id == customer_id,
                FavoritePharmacy.pharmacy_id == pharmacy_id,
            )
        )
        favorite = existing.scalar_one_or_none()
        if favorite is not None:
            return favorite

        favorite = FavoritePharmacy(customer_id=customer_id, pharmacy_id=pharmacy_id)
        db.add(favorite)
        await db.flush()
        return favorite

    # ── Remove Favorite (A3.5) ────────────────────────────────────────────────

    async def remove_favorite(
        self,
        db: AsyncSession,
        customer_id: uuid.UUID,
        pharmacy_id: uuid.UUID,
        favorite_id: uuid.UUID,
    ) -> None:
        result = await db.execute(
            select(FavoritePharmacy).where(
                FavoritePharmacy.id == favorite_id,
                FavoritePharmacy.customer_id == customer_id,
                FavoritePharmacy.pharmacy_id == pharmacy_id,
            )
        )
        favorite = result.scalar_one_or_none()
        if favorite is None:
            raise MediPickException("FAVORITE_NOT_FOUND", 404, "Favorite not found.")
        await db.delete(favorite)
        await db.flush()


pharmacy_service = PharmacyService()
