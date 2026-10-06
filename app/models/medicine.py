"""
MediPick — Medicine ORM Model (Master Catalog Entity)
Maps to the `medicines` table (ERD: MEDICINE).
Pharmacy-specific stock/pricing lives in InventoryItem, not here
(see models/inventory_item.py) — one Medicine can be stocked by many pharmacies.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Medicine(Base):
    __tablename__ = "medicines"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    # ── Classification ────────────────────────────────────────────────────────
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("medicine_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True, comment="Display name.")
    generic_name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    strength: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="e.g. 500mg.")
    dosage_form: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="e.g. Tablet, Syrup.")
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Clinical ──────────────────────────────────────────────────────────────
    requires_prescription: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Pricing (catalog-level, government-fixed) ────────────────────────────
    mrp_price: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, comment="Government MRP in LKR."
    )

    # ── Presentation ──────────────────────────────────────────────────────────
    image: Mapped[str | None] = mapped_column(Text, nullable=True, comment="CDN URL.")
    popularity: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Medicine id={self.id} name={self.name}>"
