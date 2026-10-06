"""
MediPick — Medicine Service
Business logic for the Medicines catalog: public listing/detail (A4.1, A4.2)
plus admin create/update/delete.

Catalog data (Medicine) is stored separately from per-pharmacy stock/price
(InventoryItem). Listing/detail resolve pharmacyPrice/inStock by either:
  - scoping to one pharmacy's InventoryItem row (when pharmacyId is passed), or
  - aggregating across all pharmacies (min price / any in stock) otherwise.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MediPickException
from app.models.inventory_item import InventoryItem
from app.models.medicine import Medicine
from app.models.medicine_category import MedicineCategory
from app.schemas.medicine import MedicineCreateBody, MedicineUpdateBody


class MedicineService:

    # ── List (A4.1) ───────────────────────────────────────────────────────────

    async def list_medicines(
        self,
        db: AsyncSession,
        search: str | None = None,
        category: str | None = None,
        pharmacy_id: uuid.UUID | None = None,
        is_rx_required: bool | None = None,
        in_stock: bool | None = None,
        sort: str = "popularity",
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[tuple[Medicine, str, float, bool]], int]:
        query = select(Medicine, MedicineCategory.name).join(
            MedicineCategory, Medicine.category_id == MedicineCategory.id
        )
        count_query = select(func.count()).select_from(Medicine)

        if search:
            like = f"%{search}%"
            cond = Medicine.name.ilike(like) | Medicine.generic_name.ilike(like)
            query = query.where(cond)
            count_query = count_query.where(cond)
        if category:
            query = query.where(MedicineCategory.name == category)
            count_query = count_query.join(
                MedicineCategory, Medicine.category_id == MedicineCategory.id
            ).where(MedicineCategory.name == category)
        if is_rx_required is not None:
            query = query.where(Medicine.requires_prescription == is_rx_required)
            count_query = count_query.where(Medicine.requires_prescription == is_rx_required)

        sort_map = {
            "popularity": Medicine.popularity.desc(),
            "name": Medicine.name.asc(),
        }
        query = query.order_by(sort_map.get(sort, Medicine.popularity.desc()))

        total = (await db.execute(count_query)).scalar_one()
        result = await db.execute(query)
        rows = result.all()

        # Resolve pharmacyPrice / inStock per medicine (scoped or aggregated)
        resolved: list[tuple[Medicine, str, float, bool, list[str]]] = []
        for medicine, category_name in rows:
            price, stock, available_pharmacies = await self._resolve_price_and_stock(db, medicine, pharmacy_id)
            resolved.append((medicine, category_name, price, stock, available_pharmacies))

        if in_stock is not None:
            resolved = [r for r in resolved if r[3] == in_stock]
        if sort == "price_asc":
            resolved.sort(key=lambda r: r[2])
        elif sort == "price_desc":
            resolved.sort(key=lambda r: r[2], reverse=True)

        start = (page - 1) * limit
        return resolved[start: start + limit], len(resolved) if (in_stock is not None) else total

    # ── Resolve pharmacyPrice / inStock ─────────────────────────────────────

    async def _resolve_price_and_stock(
        self, db: AsyncSession, medicine: Medicine, pharmacy_id: uuid.UUID | None
    ) -> tuple[float, bool, list[str]]:
        if pharmacy_id:
            result = await db.execute(
                select(InventoryItem).where(
                    InventoryItem.medicine_id == medicine.id,
                    InventoryItem.pharmacy_id == pharmacy_id,
                )
            )
            item = result.scalar_one_or_none()
            if item is None:
                return float(medicine.mrp_price), False, []
            in_stock = item.stock_quantity > 0
            return float(item.unit_price), in_stock, [str(pharmacy_id)] if in_stock else []

        # Get all inventory items for this medicine
        result = await db.execute(
            select(InventoryItem.pharmacy_id, InventoryItem.unit_price, InventoryItem.stock_quantity)
            .where(InventoryItem.medicine_id == medicine.id)
        )
        rows = result.all()
        
        if not rows:
            return float(medicine.mrp_price), False, []
            
        min_price = min(r.unit_price for r in rows)
        available_pharmacies = [str(r.pharmacy_id) for r in rows if r.stock_quantity > 0]
        
        return float(min_price), len(available_pharmacies) > 0, available_pharmacies

    # ── Get Single (A4.2) ────────────────────────────────────────────────────

    async def get_medicine(
        self, db: AsyncSession, medicine_id: uuid.UUID, pharmacy_id: uuid.UUID | None = None
    ) -> tuple[Medicine, str, float, bool, list[str]]:
        result = await db.execute(
            select(Medicine, MedicineCategory.name)
            .join(MedicineCategory, Medicine.category_id == MedicineCategory.id)
            .where(Medicine.id == medicine_id)
        )
        row = result.first()
        if row is None:
            raise MediPickException("MEDICINE_NOT_FOUND", 404, "Medicine not found.")
        medicine, category_name = row
        price, stock, available_pharmacies = await self._resolve_price_and_stock(db, medicine, pharmacy_id)
        return medicine, category_name, price, stock, available_pharmacies

    # ── Create (admin) ───────────────────────────────────────────────────────

    async def create_medicine(self, db: AsyncSession, body: MedicineCreateBody) -> Medicine:
        cat_result = await db.execute(
            select(MedicineCategory).where(MedicineCategory.id == uuid.UUID(body.categoryId))
        )
        if cat_result.scalar_one_or_none() is None:
            raise MediPickException("CATEGORY_NOT_FOUND", 404, "Medicine category not found.")

        medicine = Medicine(
            name=body.name,
            generic_name=body.genericName,
            brand_name=body.brandName,
            strength=body.dosage,
            dosage_form=body.dosageForm,
            manufacturer=body.manufacturer,
            category_id=uuid.UUID(body.categoryId),
            description=body.description,
            requires_prescription=body.isRxRequired,
            mrp_price=body.mrpPrice,
            image=body.image,
            popularity=body.popularity,
        )
        db.add(medicine)
        await db.flush()
        return medicine

    # ── Update (admin) ───────────────────────────────────────────────────────

    async def update_medicine(
        self, db: AsyncSession, medicine_id: uuid.UUID, body: MedicineUpdateBody
    ) -> Medicine:
        result = await db.execute(select(Medicine).where(Medicine.id == medicine_id))
        medicine = result.scalar_one_or_none()
        if medicine is None:
            raise MediPickException("MEDICINE_NOT_FOUND", 404, "Medicine not found.")

        field_map = {
            "name": "name",
            "genericName": "generic_name",
            "brandName": "brand_name",
            "dosage": "strength",
            "dosageForm": "dosage_form",
            "manufacturer": "manufacturer",
            "description": "description",
            "isRxRequired": "requires_prescription",
            "mrpPrice": "mrp_price",
            "image": "image",
            "popularity": "popularity",
        }
        for schema_field, model_field in field_map.items():
            value = getattr(body, schema_field)
            if value is not None:
                setattr(medicine, model_field, value)

        if body.categoryId is not None:
            cat_result = await db.execute(
                select(MedicineCategory).where(MedicineCategory.id == uuid.UUID(body.categoryId))
            )
            if cat_result.scalar_one_or_none() is None:
                raise MediPickException("CATEGORY_NOT_FOUND", 404, "Medicine category not found.")
            medicine.category_id = uuid.UUID(body.categoryId)

        await db.flush()
        return medicine

    # ── Delete (admin) ───────────────────────────────────────────────────────

    async def delete_medicine(self, db: AsyncSession, medicine_id: uuid.UUID) -> None:
        result = await db.execute(select(Medicine).where(Medicine.id == medicine_id))
        medicine = result.scalar_one_or_none()
        if medicine is None:
            raise MediPickException("MEDICINE_NOT_FOUND", 404, "Medicine not found.")
        await db.delete(medicine)
        await db.flush()


medicine_service = MedicineService()
