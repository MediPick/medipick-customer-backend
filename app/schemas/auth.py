"""
MediPick — Auth Pydantic Schemas
Request/response models for A1 Auth endpoints.
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserOut


# ─── A1.1 / A1.3 — OTP Request / Resend ─────────────────────────────────────

class OtpRequestBody(BaseModel):
    """POST /auth/otp/request."""
    phoneNumber: str = Field(
        ...,
        pattern=r"^\+[1-9]\d{7,14}$",
        description="E.164 format e.g. +94771234567",
        examples=["+94771234567"],
    )

class AuthChallengeBody(BaseModel):
    """POST /auth/challenge."""
    surname: str = Field(..., min_length=2, max_length=100)
    email: EmailStr | None = None
    isRecycledClaim: bool = False
    consentDataProcessing: bool = True


class OtpResendBody(BaseModel):
    """POST /auth/otp/resend"""
    phoneNumber: str = Field(
        ...,
        pattern=r"^\+[1-9]\d{7,14}$",
    )


class OtpRequestResponse(BaseModel):
    """Response body for A1.1 and A1.3"""
    message: str
    expiresIn: int = 300  # seconds


# ─── A1.2 — OTP Verify ───────────────────────────────────────────────────────

class OtpVerifyBody(BaseModel):
    """POST /auth/otp/verify"""
    phoneNumber: str = Field(..., pattern=r"^\+[1-9]\d{7,14}$")
    otp: str = Field(..., pattern=r"^\d{6}$", description="6-digit numeric OTP")


class OtpVerifyResponse(BaseModel):
    """Tokens + user profile returned on successful login"""
    accessToken: str
    refreshToken: str | None = None
    expiresIn: int = 900  # 15 minutes in seconds
    isNewUser: bool = False
    requiresChallenge: bool = False
    user: UserOut | None = None

class AuthChallengeResponse(BaseModel):
    """Tokens + user profile returned after challenge"""
    accessToken: str
    refreshToken: str
    expiresIn: int = 900
    user: UserOut


# ─── A1.4 — Token Refresh ────────────────────────────────────────────────────

class TokenRefreshBody(BaseModel):
    """POST /auth/token/refresh"""
    refreshToken: str


class TokenRefreshResponse(BaseModel):
    accessToken: str
    refreshToken: str
    expiresIn: int = 900


# ─── A1.5 — Logout ───────────────────────────────────────────────────────────

class LogoutResponse(BaseModel):
    message: str = "Logged out successfully."


# ─── A1.6 — Token Validate ───────────────────────────────────────────────────

class ValidateTokenResponse(BaseModel):
    """GET /auth/token/validate — returns live user state"""
    user: UserOut
