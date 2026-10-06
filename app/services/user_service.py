"""
MediPick — User Service
A2.4 / A2.5 (phone number change via OTP to the *new* number) and A2.6
(Expo push token registration).
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import MediPickException
from app.core.security import generate_otp, hash_otp, verify_otp_hash
from app.core.timeutil import as_aware, utcnow
from app.models.customer import Customer
from app.models.user import User
from app.services.otp_service import print_dev_otp, reject_wrong_guess


class UserService:

    async def _ensure_phone_free(self, db: AsyncSession, user: User, phone_number: str) -> None:
        taken = await db.execute(select(User.id).where(User.phone_number == phone_number, User.id != user.id))
        if taken.first() is not None:
            raise MediPickException("PHONE_IN_USE", 409, "That phone number already belongs to another account.")

    # ── A2.4 ──────────────────────────────────────────────────────────────────

    async def initiate_phone_change(
        self, db: AsyncSession, user: User, customer: Customer, new_phone: str
    ) -> None:
        if new_phone == user.phone_number:
            raise MediPickException("SAME_PHONE", 400, "That's already your phone number.")
        await self._ensure_phone_free(db, user, new_phone)

        otp = generate_otp()
        customer.pending_phone_number = new_phone
        customer.pending_phone_otp_hash = hash_otp(otp)
        customer.pending_phone_otp_expires_at = utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
        customer.pending_phone_otp_attempts = 0
        await db.flush()
        print_dev_otp(new_phone, otp, customer.pending_phone_otp_expires_at, purpose="Phone-change OTP")

    # ── A2.5 ──────────────────────────────────────────────────────────────────

    async def verify_phone_change(
        self, db: AsyncSession, user: User, customer: Customer, new_phone: str, otp: str
    ) -> None:
        if (
            customer.pending_phone_number != new_phone
            or not customer.pending_phone_otp_hash
            or customer.pending_phone_otp_expires_at is None
        ):
            raise MediPickException("NO_PENDING_PHONE_CHANGE", 400, "Request a code for this number first.")

        if as_aware(customer.pending_phone_otp_expires_at) < utcnow():
            raise MediPickException("OTP_EXPIRED", 400, "That code has expired. Please request a new one.")

        if not verify_otp_hash(otp, customer.pending_phone_otp_hash):
            customer.pending_phone_otp_attempts += 1

            def burn() -> None:
                customer.pending_phone_number = None
                customer.pending_phone_otp_hash = None
                customer.pending_phone_otp_expires_at = None

            await reject_wrong_guess(db, customer.pending_phone_otp_attempts, burn)

        # Someone may have claimed the number while the code was in flight.
        await self._ensure_phone_free(db, user, new_phone)
        user.phone_number = new_phone
        customer.pending_phone_number = None
        customer.pending_phone_otp_hash = None
        customer.pending_phone_otp_expires_at = None
        customer.pending_phone_otp_attempts = 0
        await db.flush()

    # ── A2.6 ──────────────────────────────────────────────────────────────────

    async def register_push_token(self, db: AsyncSession, customer: Customer, push_token: str) -> None:
        customer.push_token = push_token
        await db.flush()


user_service = UserService()
