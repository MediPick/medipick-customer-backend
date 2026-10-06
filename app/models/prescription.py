"""
MediPick — Prescription ORM Model
Maps to the `prescriptions` table (ERD: PRESCRIPTION).
The uploaded image itself lives in file storage (app/core/storage.py);
this row holds the storage key plus the AI clarity-check results.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models._types import str_enum


class PrescriptionStatus(str, enum.Enum):
    PRESCRIPTION_VALIDATION = "PRESCRIPTION_VALIDATION"          # AI check running
    WAITING_PHARMACY_CONFIRMATION = "WAITING_PHARMACY_CONFIRMATION"  # passed, pharmacist to review
    REJECTED = "REJECTED"                                        # not a usable prescription file
    AWAITING_PRESCRIPTION_UPLOAD = "AWAITING_PRESCRIPTION_UPLOAD"  # too unclear — re-upload


class Prescription(Base):
    __tablename__ = "prescriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    pharmacy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id", ondelete="SET NULL"), nullable=True,
        comment="Optional pharmacy pre-selected at upload time.",
    )

    patient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    file_keys: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[PrescriptionStatus] = mapped_column(
        str_enum(PrescriptionStatus), nullable=False, default=PrescriptionStatus.PRESCRIPTION_VALIDATION,
    )
    ai_clarity_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    ai_checks: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pharmacist_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_purged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Prescription id={self.id} status={self.status}>"
