"""
MediPick — A1 Auth Endpoints (Updated for User + Customer split)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.exceptions import MediPickException
from app.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.auth import (
    LogoutResponse,
    OtpRequestBody,
    OtpRequestResponse,
    OtpResendBody,
    OtpVerifyBody,
    OtpVerifyResponse,
    TokenRefreshBody,
    TokenRefreshResponse,
    ValidateTokenResponse,
)
from app.schemas.common import SuccessResponse
from app.schemas.user import UserOut
from app.services.auth_service import auth_service
from app.services.otp_service import otp_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/otp/request", response_model=SuccessResponse[OtpRequestResponse], summary="A1.1 — Request OTP")
async def request_otp(body: OtpRequestBody, db: AsyncSession = Depends(get_db)):
    """Upserts user + customer profile, generates OTP (printed to terminal in dev)."""
    user, customer = await auth_service.upsert_user_and_customer(
        db=db,
        phone_number=body.phoneNumber,
        username=body.surname,
        email=str(body.email) if body.email else None,
        consent_data_processing=body.consentDataProcessing,
    )
    await otp_service.request_otp(db=db, customer=customer, phone_number=body.phoneNumber)
    return SuccessResponse(data=OtpRequestResponse(message=f"OTP sent to {body.phoneNumber}", expiresIn=300))


@router.post("/otp/verify", response_model=SuccessResponse[OtpVerifyResponse], summary="A1.2 — Verify OTP → tokens")
async def verify_otp(body: OtpVerifyBody, db: AsyncSession = Depends(get_db)):
    """Validates OTP → marks verified, resets strikes → issues JWT + refresh token."""
    user_result = await db.execute(select(User).where(User.phone_number == body.phoneNumber))
    user = user_result.scalar_one_or_none()
    if not user:
        raise MediPickException("USER_NOT_FOUND", 404, "User not found.")

    cust_result = await db.execute(select(Customer).where(Customer.user_id == user.id))
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise MediPickException("PROFILE_NOT_FOUND", 404, "Customer profile not found.")

    await otp_service.verify_otp(db=db, customer=customer, plain_otp=body.otp)
    
    access_token, refresh_token = await auth_service.issue_tokens(db=db, user=user, customer=customer)

    return SuccessResponse(data=OtpVerifyResponse(
        accessToken=access_token,
        refreshToken=refresh_token,
        expiresIn=900,
        user=UserOut.from_orm_customer(customer, user),
    ))


@router.post("/otp/resend", response_model=SuccessResponse[OtpRequestResponse], summary="A1.3 — Resend OTP")
async def resend_otp(body: OtpResendBody, db: AsyncSession = Depends(get_db)):
    """Invalidates previous OTP and issues a new one."""
    user_result = await db.execute(select(User).where(User.phone_number == body.phoneNumber))
    user = user_result.scalar_one_or_none()
    if not user:
        raise MediPickException("USER_NOT_FOUND", 404, "User not found.")

    cust_result = await db.execute(select(Customer).where(Customer.user_id == user.id))
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise MediPickException("PROFILE_NOT_FOUND", 404, "Customer profile not found.")

    await otp_service.request_otp(db=db, customer=customer, phone_number=body.phoneNumber)
    return SuccessResponse(data=OtpRequestResponse(message=f"New OTP sent to {body.phoneNumber}", expiresIn=300))


@router.post("/token/refresh", response_model=SuccessResponse[TokenRefreshResponse], summary="A1.4 — Refresh token")
async def refresh_token(body: TokenRefreshBody, db: AsyncSession = Depends(get_db)):
    """Rotates the refresh token and issues a new JWT + refresh token pair."""
    _, _, new_access, new_refresh = await auth_service.rotate_refresh_token(
        db=db, raw_refresh_token=body.refreshToken
    )
    return SuccessResponse(data=TokenRefreshResponse(accessToken=new_access, refreshToken=new_refresh, expiresIn=900))


@router.post("/logout", response_model=SuccessResponse[LogoutResponse], summary="A1.5 — Logout")
async def logout(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Revokes all refresh tokens for the authenticated user."""
    await auth_service.revoke_all_tokens(db=db, user=current_user)
    return SuccessResponse(data=LogoutResponse())


@router.get("/token/validate", response_model=SuccessResponse[ValidateTokenResponse], summary="A1.6 — Validate token")
async def validate_token(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Returns live user state. Called by SplashScreen on app boot."""
    cust_result = await db.execute(select(Customer).where(Customer.user_id == current_user.id))
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise MediPickException("PROFILE_NOT_FOUND", 404, "Customer profile not found.")
    return SuccessResponse(data=ValidateTokenResponse(user=UserOut.from_orm_customer(customer, current_user)))
