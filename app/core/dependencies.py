"""
MediPick — FastAPI Dependencies (Updated for User + Customer split)
"""
from __future__ import annotations

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MediPickException
from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extracts and validates Bearer JWT → returns the authenticated User.
    sub in JWT = user.id (users table PK).
    Use this for any role (CUSTOMER, PHARMACIST, etc.).
    """
    if credentials is None:
        raise MediPickException("TOKEN_MISSING", 401, "Authorization header is required.")

    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        raise MediPickException("TOKEN_INVALID", 401, "Invalid or expired access token.")

    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise MediPickException("TOKEN_INVALID", 401, "Token payload is malformed.")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise MediPickException("TOKEN_INVALID", 401, "Token subject is not a valid UUID.")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise MediPickException("TOKEN_INVALID", 401, "User not found.")
    if not user.is_active:
        raise MediPickException("ACCOUNT_SUSPENDED", 403, "This account has been suspended.")

    return user


def require_roles(*roles):
    """Dependency factory: the authenticated user must hold one of `roles`."""

    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise MediPickException("FORBIDDEN", 403, "You don't have permission to do this.")
        return user

    return dependency


async def get_current_customer_user(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Extends get_current_user — also fetches and returns the Customer profile.
    Only valid for users with role=CUSTOMER.
    Returns (user, customer) tuple.
    """
    from app.models.customer import Customer
    from app.models.user import UserRole

    if user.role != UserRole.CUSTOMER:
        raise MediPickException(
            "FORBIDDEN", 403, "This endpoint is only accessible to customers."
        )

    result = await db.execute(
        select(Customer).where(Customer.user_id == user.id)
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise MediPickException("PROFILE_NOT_FOUND", 404, "Customer profile not found.")

    return user, customer


async def get_optional_current_customer(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    Like get_current_customer_user, but returns None instead of raising when
    there's no token, an invalid token, or the caller isn't a customer.
    For public endpoints that personalize their response when authenticated
    (e.g. GET /pharmacies resolving isFavorite/favoriteId).
    Returns (user, customer) tuple or None.
    """
    from app.models.customer import Customer
    from app.models.user import UserRole

    if credentials is None:
        return None

    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        return None

    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        return None

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or user.role != UserRole.CUSTOMER:
        return None

    cust_result = await db.execute(select(Customer).where(Customer.user_id == user.id))
    customer = cust_result.scalar_one_or_none()
    if customer is None:
        return None

    return user, customer
