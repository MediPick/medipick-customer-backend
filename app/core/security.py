"""
MediPick — Security Utilities
JWT creation/verification, OTP generation/hashing, refresh token hashing.
"""
from __future__ import annotations

import hashlib
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ─── Password / OTP Context ───────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─── OTP ─────────────────────────────────────────────────────────────────────

def generate_otp() -> str:
    """Returns a cryptographically random 6-digit OTP string."""
    return "".join(secrets.choice(string.digits) for _ in range(6))


def hash_otp(otp: str) -> str:
    """bcrypt-hash the OTP for storage in otp_requests table."""
    return pwd_context.hash(otp)


def verify_otp_hash(plain_otp: str, hashed_otp: str) -> bool:
    """Verify a plain OTP against its stored bcrypt hash."""
    return pwd_context.verify(plain_otp, hashed_otp)


# ─── Refresh Token ────────────────────────────────────────────────────────────

def generate_refresh_token() -> str:
    """Returns a new opaque UUID4 refresh token (raw, un-hashed)."""
    return str(uuid.uuid4())


def hash_refresh_token(raw_token: str) -> str:
    """SHA-256 hex digest of the raw refresh token for DB storage."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


# ─── JWT Access Token ─────────────────────────────────────────────────────────

def create_access_token(
    user_id: str,
    phone_number: str,
    role: str = "CUSTOMER",
) -> str:
    """
    Creates a signed JWT access token.
    Payload matches the spec:
      { sub, role, phone, iat, exp }
    sub = user.id (the users table PK — not customer.id)
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),
        "role": role,
        "phone": phone_number,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    """
    Decodes and verifies a JWT access token.
    Raises jose.JWTError on invalid/expired tokens.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
