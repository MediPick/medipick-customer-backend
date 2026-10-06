"""
MediPick — A2 Users Endpoints
Customer profile management.

A2.1  GET   /users/me               — Get profile
A2.2  PATCH /users/me               — Update surname/email
A2.3  PATCH /users/me/preferences   — Toggle notification preferences
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_customer_user
from app.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.common import MessageResponse, SuccessResponse
from app.schemas.user import (
    InitiatePhoneChangeRequest,
    RegisterPushTokenRequest,
    UpdatePreferencesRequest,
    UpdateUserRequest,
    UserOut,
    VerifyPhoneChangeRequest,
)
from app.services.user_service import user_service

router = APIRouter(prefix="/users", tags=["Users"])


# ─── A2.1 — GET /users/me ────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=SuccessResponse[UserOut],
    status_code=status.HTTP_200_OK,
    summary="A2.1 — Get authenticated customer profile",
)
async def get_me(
    current_customer: tuple[User, Customer] = Depends(get_current_customer_user),
) -> SuccessResponse[UserOut]:
    """Returns the full profile of the currently authenticated customer."""
    user, customer = current_customer
    return SuccessResponse(data=UserOut.from_orm_customer(customer, user))


# ─── A2.2 — PATCH /users/me ──────────────────────────────────────────────────

@router.patch(
    "/me",
    response_model=SuccessResponse[UserOut],
    status_code=status.HTTP_200_OK,
    summary="A2.2 — Update username or email",
)
async def update_me(
    body: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    current_customer: tuple[User, Customer] = Depends(get_current_customer_user),
) -> SuccessResponse[UserOut]:
    """Updates mutable profile fields (username, email)."""
    user, customer = current_customer
    
    if body.surname is not None:
        customer.username = body.surname
    if body.email is not None:
        user.email = str(body.email)

    await db.flush()
    return SuccessResponse(data=UserOut.from_orm_customer(customer, user))


# ─── A2.3 — PATCH /users/me/preferences ──────────────────────────────────────

@router.patch(
    "/me/preferences",
    response_model=SuccessResponse[UserOut],
    status_code=status.HTTP_200_OK,
    summary="A2.3 — Toggle notification preferences",
)
async def update_preferences(
    body: UpdatePreferencesRequest,
    db: AsyncSession = Depends(get_db),
    current_customer: tuple[User, Customer] = Depends(get_current_customer_user),
) -> SuccessResponse[UserOut]:
    """Toggles push notification and email receipt preferences."""
    user, customer = current_customer
    
    if body.pushNotificationsEnabled is not None:
        customer.push_notifications_enabled = body.pushNotificationsEnabled
    if body.emailReceiptsEnabled is not None:
        customer.email_receipts_enabled = body.emailReceiptsEnabled

    await db.flush()
    return SuccessResponse(data=UserOut.from_orm_customer(customer, user))


# ─── A2.4 — PATCH /users/me/phone ────────────────────────────────────────────

@router.patch(
    "/me/phone",
    response_model=SuccessResponse[MessageResponse],
    summary="A2.4 — Start a phone number change (OTP sent to the new number)",
)
async def initiate_phone_change(
    body: InitiatePhoneChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_customer: tuple[User, Customer] = Depends(get_current_customer_user),
) -> SuccessResponse[MessageResponse]:
    user, customer = current_customer
    await user_service.initiate_phone_change(db, user, customer, body.newPhoneNumber)
    return SuccessResponse(data=MessageResponse(message=f"OTP sent to {body.newPhoneNumber}"))


# ─── A2.5 — POST /users/me/phone/verify ──────────────────────────────────────

@router.post(
    "/me/phone/verify",
    response_model=SuccessResponse[MessageResponse],
    summary="A2.5 — Confirm the phone number change with the OTP",
)
async def verify_phone_change(
    body: VerifyPhoneChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_customer: tuple[User, Customer] = Depends(get_current_customer_user),
) -> SuccessResponse[MessageResponse]:
    user, customer = current_customer
    await user_service.verify_phone_change(db, user, customer, body.newPhoneNumber, body.otp)
    return SuccessResponse(data=MessageResponse(message="Phone number updated."))


# ─── A2.6 — POST /users/me/push-token ────────────────────────────────────────

@router.post(
    "/me/push-token",
    response_model=SuccessResponse[MessageResponse],
    summary="A2.6 — Register the device's Expo push token",
)
async def register_push_token(
    body: RegisterPushTokenRequest,
    db: AsyncSession = Depends(get_db),
    current_customer: tuple[User, Customer] = Depends(get_current_customer_user),
) -> SuccessResponse[MessageResponse]:
    _, customer = current_customer
    await user_service.register_push_token(db, customer, body.pushToken)
    return SuccessResponse(data=MessageResponse(message="Push token registered."))
