"""
MediPick — Order ORM Models
Maps to `orders`, `order_items` and `order_ratings` (ERD: ORDER, ORDER_ITEM, REVIEW).

The order lifecycle is a finite-state machine; its states mirror FSMOrderState
in src/types/index.ts. All state changes go through app/services/order_fsm.py
so their side effects (notifications, pickup codes, stock release, refunds)
can never be skipped.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models._types import str_enum


class OrderType(str, enum.Enum):
    OTC = "OTC"
    PRESCRIPTION = "PRESCRIPTION"
    MIXED = "MIXED"


class OrderState(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PRESCRIPTION_VALIDATION = "PRESCRIPTION_VALIDATION"
    AWAITING_PRESCRIPTION_UPLOAD = "AWAITING_PRESCRIPTION_UPLOAD"
    WAITING_PHARMACY_CONFIRMATION = "WAITING_PHARMACY_CONFIRMATION"
    WAITING_CUSTOMER_CONFIRMATION = "WAITING_CUSTOMER_CONFIRMATION"
    PREPARING = "PREPARING"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"
    ISSUE_REPORTED = "ISSUE_REPORTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"
    REUPLOAD_REQUESTED = "REUPLOAD_REQUESTED"


class PaymentMethod(str, enum.Enum):
    ONLINE = "ONLINE"
    PAY_AT_COUNTER = "PAY_AT_COUNTER"


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("customer_id", "idempotency_key", name="uq_orders_customer_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    prescription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prescriptions.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    original_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True,
        comment="Set when this order was created via reorder.",
    )

    order_type: Mapped[OrderType] = mapped_column(str_enum(OrderType, 20), nullable=False)
    state: Mapped[OrderState] = mapped_column(str_enum(OrderState), nullable=False, index=True)

    # ── Payment ───────────────────────────────────────────────────────────────
    payment_method: Mapped[PaymentMethod | None] = mapped_column(str_enum(PaymentMethod, 20), nullable=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    refund_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    refund_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # ── Money (LKR) ───────────────────────────────────────────────────────────
    total_mrp: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)

    # ── Customer choices / pharmacy feedback ─────────────────────────────────
    allow_generic_substitution: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    customer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Pickup ────────────────────────────────────────────────────────────────
    pickup_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    pickup_code_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pickup_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pickup_extension_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── SLA deadlines ─────────────────────────────────────────────────────────
    sla_pharmacy_review_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_customer_confirm_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships (eager — async sessions can't lazy-load on attribute access) ──
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan",
        lazy="selectin", order_by="OrderItem.line_no",
    )
    rating: Mapped["OrderRating | None"] = relationship(
        "OrderRating", back_populates="order", uselist=False,
        cascade="all, delete-orphan", lazy="selectin",
    )
    pharmacy: Mapped["Pharmacy"] = relationship("Pharmacy", lazy="selectin")  # noqa: F821
    prescription: Mapped["Prescription | None"] = relationship("Prescription", lazy="selectin")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Order {self.order_number} state={self.state}>"


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    medicine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medicines.id", ondelete="SET NULL"), nullable=True,
    )
    # Set only when stock was actually reserved from this inventory row, so a
    # cancellation knows exactly what to give back.
    inventory_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True,
    )

    # Snapshot of the medicine at order time — orders must still render if the
    # catalog entry is later edited or deleted.
    medicine_name: Mapped[str] = mapped_column(String(255), nullable=False)
    generic_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dosage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image: Mapped[str | None] = mapped_column(Text, nullable=True)

    quantity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    unit_mrp: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    is_generic_substitute: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    original_prescribed: Mapped[str | None] = mapped_column(String(255), nullable=True)

    order: Mapped[Order] = relationship("Order", back_populates="items")


class OrderRating(Base):
    __tablename__ = "order_ratings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False,
    )
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    overall_rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    service_rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    availability_rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    pickup_rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    order: Mapped[Order] = relationship("Order", back_populates="rating")
