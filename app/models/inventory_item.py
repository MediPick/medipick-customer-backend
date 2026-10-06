"""
MediPick — Inventory Item ORM Model (Per-Pharmacy Stock/Pricing Entity)
Maps to the `inventory_items` table (ERD: INVENTORY_ITEM).
One row per (pharmacy, medicine) pair — this is where stock_quantity and
unit_price actually live, since those vary by pharmacy.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, SmallInteger, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("pharmacy_id", "medicine_id", name="uq_inventory_pharmacy_medicine"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    medicine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medicines.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    stock_quantity: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    unit_price: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, comment="Pharmacy selling price in LKR."
    )
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_synced: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<InventoryItem id={self.id} pharmacy_id={self.pharmacy_id} medicine_id={self.medicine_id}>"
