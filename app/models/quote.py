"""
MediPick — Quote ORM Models
Maps to `quotes` and `quote_items`. A pharmacist prices an order (typically a
prescription order) with a quote; the customer then accepts or declines it.
An order can accumulate several quotes over time (declined → revised), but at
most one is PENDING at once.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models._types import str_enum


class QuoteStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id", ondelete="CASCADE"), nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    status: Mapped[QuoteStatus] = mapped_column(str_enum(QuoteStatus, 20), nullable=False, default=QuoteStatus.PENDING)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    total_mrp: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    items: Mapped[list["QuoteItem"]] = relationship(
        "QuoteItem", back_populates="quote", cascade="all, delete-orphan",
        lazy="selectin", order_by="QuoteItem.line_no",
    )
    pharmacy: Mapped["Pharmacy"] = relationship("Pharmacy", lazy="selectin")  # noqa: F821


class QuoteItem(Base):
    __tablename__ = "quote_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    medicine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medicines.id", ondelete="SET NULL"), nullable=True,
    )
    medicine_name: Mapped[str] = mapped_column(String(255), nullable=False)
    generic_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dosage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quantity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    mrp: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    quoted_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    is_alternative: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    original_prescribed: Mapped[str | None] = mapped_column(String(255), nullable=True)

    quote: Mapped[Quote] = relationship("Quote", back_populates="items")
