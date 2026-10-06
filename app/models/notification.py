"""
MediPick — Notification ORM Model
Maps to `notifications` (ERD: NOTIFICATION). Created by the services whenever
something the customer cares about happens (see notification_service.notify).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models._types import str_enum


class NotificationType(str, enum.Enum):
    ORDER_STATUS_CHANGED = "ORDER_STATUS_CHANGED"
    QUOTE_RECEIVED = "QUOTE_RECEIVED"
    PICKUP_READY = "PICKUP_READY"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    PRESCRIPTION_APPROVED = "PRESCRIPTION_APPROVED"
    PRESCRIPTION_REJECTED = "PRESCRIPTION_REJECTED"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    ISSUE_RESOLVED = "ISSUE_RESOLVED"
    SYSTEM = "SYSTEM"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True,
    )
    prescription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prescriptions.id", ondelete="SET NULL"), nullable=True,
    )

    notification_type: Mapped[NotificationType] = mapped_column(str_enum(NotificationType), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message_body: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True,
    )
