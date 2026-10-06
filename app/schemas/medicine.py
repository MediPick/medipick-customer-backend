"""
MediPick — Medicine Pydantic Schemas
Request/response models for the Medicines domain (A4 + admin CRUD).
Field names match src/api/medicinesApi.ts on the client. The backend stores
catalog data (Medicine) separately from per-pharmacy stock/price (InventoryItem,
see app/models/inventory_item.py) but the API still returns one flat shape.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.medicine import Medicine


# ─── Shared ───────────────────────────────────────────────────────────────────

class MedicineOut(BaseModel):
    """Matches the client's `Medicine` interface."""
    id: str
    name: str
    genericName: str
    brandName: str | None
    dosage: str | None
    category: str
    description: str | None
    isRxRequired: bool
    mrpPrice: float
    pharmacyPrice: float
    inStock: bool
    image: str | None
    popularity: int
    availableAtPharmacyIds: list[str] = Field(default_factory=list)

    @staticmethod
    def from_catalog_and_stock(
        m: Medicine,
        category_name: str,
        pharmacy_price: float,
        in_stock: bool,
        available_pharmacies: list[str],
    ) -> "MedicineOut":
        """
        pharmacy_price / in_stock are resolved by the service layer:
        - scoped to one pharmacy when `pharmacyId` was passed in the query
        - aggregated across all pharmacies (min price / any in stock) otherwise
        """
        return MedicineOut(
            id=str(m.id),
            name=m.name,
            genericName=m.generic_name,
            brandName=m.brand_name,
            dosage=m.strength,
            category=category_name,
            description=m.description,
            isRxRequired=m.requires_prescription,
            mrpPrice=float(m.mrp_price),
            pharmacyPrice=pharmacy_price,
            inStock=in_stock,
            image=m.image,
            popularity=m.popularity,
            availableAtPharmacyIds=available_pharmacies,
        )


# ─── A4.1 — List Medicines (🔓 public) ────────────────────────────────────────
# Query params are parsed directly in the endpoint (search, category, pharmacyId,
# isRxRequired, inStock, sort, page, limit) — no body schema needed.


# ─── Admin — Create ───────────────────────────────────────────────────────────

class MedicineCreateBody(BaseModel):
    """POST /medicines (admin) — creates a catalog entry. Stock/pricing per
    pharmacy is managed separately via the (future) inventory domain."""
    name: str = Field(..., min_length=1, max_length=255)
    genericName: str = Field(..., min_length=1, max_length=255)
    brandName: str | None = None
    dosage: str | None = Field(None, max_length=100, description="Maps to strength.")
    dosageForm: str | None = Field(None, max_length=100)
    manufacturer: str | None = Field(None, max_length=255)
    categoryId: str = Field(..., description="MedicineCategory UUID.")
    description: str | None = None
    isRxRequired: bool = False
    mrpPrice: float = Field(..., ge=0)
    image: str | None = None
    popularity: int = Field(0, ge=0, le=100)


# ─── Admin — Update ───────────────────────────────────────────────────────────

class MedicineUpdateBody(BaseModel):
    """PATCH /medicines/{medicineId} (admin) — all fields optional (partial update)."""
    name: str | None = Field(None, min_length=1, max_length=255)
    genericName: str | None = Field(None, min_length=1, max_length=255)
    brandName: str | None = None
    dosage: str | None = Field(None, max_length=100)
    dosageForm: str | None = Field(None, max_length=100)
    manufacturer: str | None = Field(None, max_length=255)
    categoryId: str | None = None
    description: str | None = None
    isRxRequired: bool | None = None
    mrpPrice: float | None = Field(None, ge=0)
    image: str | None = None
    popularity: int | None = Field(None, ge=0, le=100)


# ─── Admin — Delete ───────────────────────────────────────────────────────────

class MedicineDeleteResponse(BaseModel):
    message: str = "Medicine deleted successfully."
