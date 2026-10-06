"""
MediPick — Pharmacy ORM Model
Maps to the `pharmacies` table.

Columns beyond the ERD's core PHARMACY entity (pharmacist_name, pharmacist_reg_no,
is_open, has_offer, offer_tag, estimated_response_time, rating_total, rating_count,
image) are denormalized directly onto Pharmacy as a pragmatic simplification —
the ERD's separate PHARMACY_STAFF (pharmacist-in-charge), OPERATING_HOURS,
STORE_PROMOTION and REVIEW entities aren't built yet. Revisit once those domains
exist, following backend-layered-architecture.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PharmacyStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"


class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    # ── Identity / Registration ───────────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    registration_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    nmra_license: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pharmacist_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pharmacist_reg_no: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Contact / Location ────────────────────────────────────────────────────
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)

    # ── Storefront presentation ───────────────────────────────────────────────
    image: Mapped[str | None] = mapped_column(Text, nullable=True, comment="CDN URL.")
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    estimated_response_time: Mapped[str] = mapped_column(
        String(50), default="5 - 15 mins", nullable=False
    )
    has_offer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    offer_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rating_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="Sum of ratings.")
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[PharmacyStatus] = mapped_column(
        Enum(PharmacyStatus, name="pharmacy_status_enum"),
        nullable=False,
        default=PharmacyStatus.PENDING,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Pharmacy id={self.id} name={self.name}>"
