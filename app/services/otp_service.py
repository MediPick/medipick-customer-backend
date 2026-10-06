"""
MediPick — OTP Service
Handles OTP generation, bcrypt hashing, and verification using the Customer model.
Wrong guesses are capped at OTP_MAX_ATTEMPTS per issued code; after that the
code is burned and the customer must request a new one.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import MediPickException
from app.core.security import generate_otp, hash_otp, verify_otp_hash
from app.models.customer import Customer


def print_dev_otp(phone_number: str, otp: str, expires_at: datetime, purpose: str = "OTP") -> None:
    """No SMS provider is wired in yet — in dev the code is printed for the tester."""
    print(
        f"\n{'='*50}\n"
        f"  [DEV] {purpose} for {phone_number}: {otp}\n"
        f"  Expires at: {expires_at.strftime('%H:%M:%S UTC')}\n"
        f"{'='*50}\n"
    )


async def reject_wrong_guess(db: AsyncSession, attempts_so_far: int, burn_code) -> None:
    """
    Records a wrong guess and raises. Commits first: raising rolls the request's
    transaction back, which would otherwise silently discard the attempt count.
    """
    if attempts_so_far >= settings.OTP_MAX_ATTEMPTS:
        burn_code()
        await db.commit()
        raise MediPickException(
            "OTP_ATTEMPTS_EXCEEDED", 429, "Too many incorrect codes. Please request a new OTP.",
        )
    await db.commit()
    remaining = settings.OTP_MAX_ATTEMPTS - attempts_so_far
    raise MediPickException(
        "OTP_INVALID", 400, f"The OTP you entered is incorrect. {remaining} attempt(s) left.",
    )


class OtpService:

    async def request_otp(
        self, db: AsyncSession, customer: Customer, phone_number: str
    ) -> str:
        """
        Generates a 6-digit OTP, hashes it, and stores it directly on the Customer profile.
        Sets the expiration time based on OTP_EXPIRE_MINUTES.
        `phone_number` is passed in (not read off `customer`) since phone_number
        lives on the `users` table, not `customers`.
        """
        raw_otp = generate_otp()
        customer.otp_hash = hash_otp(raw_otp)
        customer.otp_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.OTP_EXPIRE_MINUTES
        )
        customer.otp_attempts = 0

        await db.flush()
        print_dev_otp(phone_number, raw_otp, customer.otp_expires_at)
        return raw_otp

    async def verify_otp(
        self, db: AsyncSession, customer: Customer, plain_otp: str
    ) -> None:
        """
        Validates the given OTP against the customer's stored hash.
        Raises MediPickException on failure.
        Clears the OTP fields on success.
        """
        now = datetime.now(timezone.utc)

        if not customer.otp_hash or not customer.otp_expires_at:
            raise MediPickException(
                "OTP_INVALID", 400, "No OTP request found for this number. Please request a new one."
            )

        # Handle timezone-awareness comparison properly
        expires_at = customer.otp_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < now:
            raise MediPickException(
                "OTP_EXPIRED", 400, "OTP has expired. Please request a new one."
            )

        if not verify_otp_hash(plain_otp, customer.otp_hash):
            customer.otp_attempts += 1

            def burn() -> None:
                customer.otp_hash = None
                customer.otp_expires_at = None

            await reject_wrong_guess(db, customer.otp_attempts, burn)

        # Success! Mark as used by clearing the fields
        customer.otp_hash = None
        customer.otp_expires_at = None
        customer.otp_attempts = 0
        await db.flush()


otp_service = OtpService()
