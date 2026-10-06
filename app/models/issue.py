"""
MediPick — Issue ORM Model
Maps to `issues`: a customer's post-pickup complaint about a completed order.
At most one issue per order.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models._types import str_enum


class IssueType(str, enum.Enum):
    MISSING_MEDICINE = "Missing medicine"
    WRONG_MEDICINE = "Wrong medicine"
    DAMAGED_EXPIRED = "Damaged / Expired"
    WRONG_QUANTITY = "Wrong quantity"
    OTHER = "Other"


class IssueStatus(str, enum.Enum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    issue_type: Mapped[IssueType] = mapped_column(str_enum(IssueType), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_file_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[IssueStatus] = mapped_column(str_enum(IssueStatus, 20), nullable=False, default=IssueStatus.OPEN)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
