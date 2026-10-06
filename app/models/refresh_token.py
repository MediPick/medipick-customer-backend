"""
MediPick — RefreshToken ORM Model
Maps to `refresh_tokens` table.
Now references `users.id` (not customers) since all roles can have refresh tokens.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # FK to users (not customers) — any role can have tokens
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token_hash: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
        index=True,
        comment="SHA-256 hex digest of the raw opaque token UUID.",
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="NOW() + REFRESH_TOKEN_EXPIRE_DAYS",
    )

    revoked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="True after token is used (rotation) or on logout.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="refresh_tokens"
    )

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} revoked={self.revoked}>"
