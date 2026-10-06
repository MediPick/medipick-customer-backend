"""
MediPick — Customer ORM Model (Profile Entity)
Maps to the `customers` table.
Linked 1:1 to `users` (where user.role = CUSTOMER).
Contains all customer-specific profile and preference data.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── FK to users (1:1) ─────────────────────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,        # enforces 1:1 with users
        nullable=False,
        index=True,
        comment="References users.id. One customer profile per user account.",
    )

    # ── Profile ───────────────────────────────────────────────────────────────
    username: Mapped[str] = mapped_column(String(100), nullable=False)

    # ── Authentication (OTP) ──────────────────────────────────────────────────
    otp_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    otp_attempts: Mapped[int] = mapped_column(
        SmallInteger, default=0, nullable=False,
        comment="Wrong guesses against the current login OTP; capped at OTP_MAX_ATTEMPTS.",
    )

    # ── Pending phone number change (A2.4 → A2.5) ────────────────────────────
    # Kept separate from the login OTP so the two flows can never clobber each other.
    pending_phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pending_phone_otp_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pending_phone_otp_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pending_phone_otp_attempts: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)

    # ── Trust & Policy ────────────────────────────────────────────────────────
    consent_data_processing: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    no_show_count: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    
    is_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="Set to True on first successful OTP verify.",
    )
    strike_limit: Mapped[int] = mapped_column(
        SmallInteger,
        default=5,
        nullable=False,
    )
    is_locked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="True when no_show_count >= strike_limit.",
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Lock expires after LOCKOUT_HOURS. Null when not locked.",
    )

    # ── Notifications ─────────────────────────────────────────────────────────
    push_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    email_receipts_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    push_token: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Expo push notification token. Updated on app launch.",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship(  # noqa: F821
        "User",
        back_populates="customer_profile",
    )

    def __repr__(self) -> str:
        return f"<Customer id={self.id} user_id={self.user_id}>"
