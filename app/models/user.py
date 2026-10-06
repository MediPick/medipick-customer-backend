"""
MediPick — User ORM Model (Auth Entity)
Maps to the `users` table.
Every person who logs into MediPick (any role) has a User record.
The role determines which profile table they link to (customers, pharmacists, etc.)
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    PHARMACIST = "PHARMACIST"
    PHARMACY_STAFF = "PHARMACY_STAFF"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"


class User(Base):
    """
    Core authentication entity.
    All roles share this table — role claim is embedded in the JWT.
    Profile data lives in role-specific tables (customers, pharmacist_profiles, etc.)
    """
    __tablename__ = "users"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    phone_number: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment="E.164 format e.g. +94771234567. Primary login identifier.",
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        comment="Optional email address.",
    )
    credential_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="For roles that use password authentication.",
    )

    # ── Role & Status ─────────────────────────────────────────────────────────
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"),
        nullable=False,
        default=UserRole.CUSTOMER,
        comment="Determines which profile table this user links to.",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Soft-delete / account suspension flag.",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    customer_profile: Mapped["Customer"] = relationship(  # noqa: F821
        "Customer",
        back_populates="user",
        uselist=False,   # 1:1
        cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(  # noqa: F821
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} phone={self.phone_number} role={self.role}>"
