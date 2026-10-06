"""
MediPick — User Pydantic Schemas
Used by A2 Users endpoints and embedded in auth responses.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserOut(BaseModel):
    """
    Customer profile returned to the client.
    Matches the AuthUser interface in src/api/authApi.ts.
    """
    id: uuid.UUID
    phoneNumber: str
    surname: str
    email: str | None = None
    isVerified: bool
    strikes: int
    strikeLimit: int
    isLocked: bool
    lockedUntil: datetime | None = None
    pushNotificationsEnabled: bool
    emailReceiptsEnabled: bool
    createdAt: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}

    @classmethod
    def from_orm_customer(cls, c: object, u: object) -> "UserOut":
        """Build UserOut from a Customer + User pair."""
        return cls(
            id=c.id,  # type: ignore[attr-defined]
            phoneNumber=u.phone_number,  # type: ignore[attr-defined]  ← from users table
            surname=c.username,  # type: ignore[attr-defined]  ← DB column stays `username`
            email=u.email,  # type: ignore[attr-defined] ← from users table
            isVerified=c.is_verified,  # type: ignore[attr-defined]
            strikes=c.no_show_count,  # type: ignore[attr-defined]
            strikeLimit=c.strike_limit,  # type: ignore[attr-defined]
            isLocked=c.is_locked,  # type: ignore[attr-defined]
            lockedUntil=c.locked_until,  # type: ignore[attr-defined]
            pushNotificationsEnabled=c.push_notifications_enabled,  # type: ignore[attr-defined]
            emailReceiptsEnabled=c.email_receipts_enabled,  # type: ignore[attr-defined]
            createdAt=c.created_at,  # type: ignore[attr-defined]
        )


class UpdateUserRequest(BaseModel):
    """A2.2 — PATCH /users/me. Matches UpdateProfilePayload in src/api/usersApi.ts."""
    surname: str | None = Field(None, min_length=2, max_length=100)
    email: EmailStr | None = None


class UpdatePreferencesRequest(BaseModel):
    """A2.3 — PATCH /users/me/preferences"""
    pushNotificationsEnabled: bool | None = None
    emailReceiptsEnabled: bool | None = None


_E164 = r"^\+[1-9]\d{7,14}$"


class InitiatePhoneChangeRequest(BaseModel):
    """A2.4 — PATCH /users/me/phone"""
    newPhoneNumber: str = Field(..., pattern=_E164)


class VerifyPhoneChangeRequest(BaseModel):
    """A2.5 — POST /users/me/phone/verify"""
    newPhoneNumber: str = Field(..., pattern=_E164)
    otp: str = Field(..., pattern=r"^\d{6}$")


class RegisterPushTokenRequest(BaseModel):
    """A2.6 — POST /users/me/push-token"""
    pushToken: str = Field(..., pattern=r"^Expo(nent)?PushToken\[[^\]]+\]$", max_length=255)
