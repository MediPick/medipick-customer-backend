"""
MediPick — Favorite Pharmacy ORM Model
Maps to the `favorite_pharmacies` table (ERD: FAVORITE_PHARMACY).
One row per (customer, pharmacy) bookmark.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FavoritePharmacy(Base):
    __tablename__ = "favorite_pharmacies"
    __table_args__ = (
        UniqueConstraint("customer_id", "pharmacy_id", name="uq_favorite_customer_pharmacy"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<FavoritePharmacy id={self.id} customer_id={self.customer_id} pharmacy_id={self.pharmacy_id}>"
