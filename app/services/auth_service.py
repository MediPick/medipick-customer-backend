"""
MediPick — Auth Service (Updated for User + Customer split)
Business logic for user/customer upsert, token issuance, and token rotation.

Flow:
  OTP Request → upsert_user_and_customer()
    1. Upsert into `users` (phone_number, role=CUSTOMER)
    2. Upsert into `customers` (user_id FK, surname, email)

  OTP Verify → issue_tokens()
    1. Create JWT with user.id, user.role, user.phone_number
    2. Store SHA-256 hashed refresh token in refresh_tokens (user_id FK)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import MediPickException
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.models.customer import Customer
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole


class AuthService:

    # ── Upsert User + Customer Profile ────────────────────────────────────────

    async def upsert_user_and_customer(
        self,
        db: AsyncSession,
        phone_number: str,
        username: str,
        email: str | None = None,
        consent_data_processing: bool = True,
    ) -> tuple[User, Customer]:
        """
        Step 1: Upsert into `users` (by phone_number, role=CUSTOMER).
        Step 2: Upsert into `customers` (linked via user_id FK).
        Returns (user, customer).
        """
        # ── Find Existing User by Phone ───────────────────────────────────────
        result = await db.execute(
            select(User).where(User.phone_number == phone_number)
        )
        user = result.scalar_one_or_none()

        customer = None

        if user is not None:
            # Check if this is a recycled number scenario by comparing surnames
            cust_result = await db.execute(
                select(Customer).where(Customer.user_id == user.id)
            )
            existing_customer = cust_result.scalar_one_or_none()

            if existing_customer and existing_customer.username.strip().lower() != username.strip().lower():
                # SURNAME MISMATCH (Recycled number detected)
                # Archive the old user so their medical data remains inaccessible
                user.phone_number = f"{phone_number}-archived-{user.id}"
                db.add(user)
                await db.flush()
                
                # Treat as a brand new user from here on
                user = None
                customer = None
            else:
                customer = existing_customer

        # ── Upsert Logic ──────────────────────────────────────────────────────
        if user is None:
            # Create Brand New User
            user = User(
                phone_number=phone_number,
                email=email,
                role=UserRole.CUSTOMER,
            )
            db.add(user)
            await db.flush()  # get user.id before FK reference
            
            customer = Customer(
                user_id=user.id,
                username=username,
                consent_data_processing=consent_data_processing,
            )
            db.add(customer)
        else:
            # Update Existing User
            if email:
                user.email = email
                
            if customer:
                # We don't overwrite the username here, it already matched (case-insensitive)
                # Just update consent if provided
                if consent_data_processing is not None:
                    customer.consent_data_processing = consent_data_processing
        
        await db.flush()
        return user, customer

    # ── Issue Tokens ──────────────────────────────────────────────────────────

    async def issue_tokens(
        self, db: AsyncSession, user: User, customer: Customer
    ) -> tuple[str, str]:
        """
        Issues JWT (using user.id, user.role, user.phone_number) +
        fresh opaque refresh token.
        Revokes all previous active refresh tokens for this user.
        Also marks customer as verified. (Order strikes are deliberately NOT
        reset here — otherwise logging out and back in would wipe them.)
        Returns (access_token_raw, refresh_token_raw).
        """
        # Revoke all previous refresh tokens for this user
        prev_result = await db.execute(
            select(RefreshToken).where(
                and_(
                    RefreshToken.user_id == user.id,
                    RefreshToken.revoked == False,  # noqa: E712
                )
            )
        )
        for old in prev_result.scalars().all():
            old.revoked = True

        # Update customer state on successful login
        customer.is_verified = True

        # Create JWT — sub = user.id, role = user.role, phone = user.phone_number
        access_token = create_access_token(
            user_id=str(user.id),
            phone_number=user.phone_number,
            role=user.role.value,
        )

        # Create & store refresh token
        raw_refresh = generate_refresh_token()
        refresh_token_record = RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        db.add(refresh_token_record)
        await db.flush()

        return access_token, raw_refresh

    # ── Rotate Refresh Token ──────────────────────────────────────────────────

    async def rotate_refresh_token(
        self, db: AsyncSession, raw_refresh_token: str
    ) -> tuple[User, Customer, str, str]:
        """
        Validates → revokes old token → issues new pair.
        Returns (user, customer, new_access_token, new_refresh_token).
        """
        token_hash = hash_refresh_token(raw_refresh_token)
        now = datetime.now(timezone.utc)

        rt_result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        stored = rt_result.scalar_one_or_none()

        if stored is None:
            raise MediPickException("REFRESH_TOKEN_INVALID", 401, "Refresh token not found.")
        if stored.revoked:
            raise MediPickException("REFRESH_TOKEN_INVALID", 401, "Refresh token has been revoked.")
        if stored.expires_at.replace(tzinfo=timezone.utc) < now:
            raise MediPickException("REFRESH_TOKEN_EXPIRED", 401, "Refresh token has expired. Please log in again.")

        stored.revoked = True  # Rotate: revoke old

        # Fetch user
        user_result = await db.execute(select(User).where(User.id == stored.user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            raise MediPickException("TOKEN_INVALID", 401, "User not found.")

        # Fetch customer profile
        cust_result = await db.execute(select(Customer).where(Customer.user_id == user.id))
        customer = cust_result.scalar_one_or_none()
        if customer is None:
            raise MediPickException("TOKEN_INVALID", 401, "Customer profile not found.")

        new_access, new_refresh = await self.issue_tokens(db, user, customer)
        return user, customer, new_access, new_refresh

    # ── Revoke All Tokens (Logout) ────────────────────────────────────────────

    async def revoke_all_tokens(self, db: AsyncSession, user: User) -> None:
        result = await db.execute(
            select(RefreshToken).where(
                and_(
                    RefreshToken.user_id == user.id,
                    RefreshToken.revoked == False,  # noqa: E712
                )
            )
        )
        for token in result.scalars().all():
            token.revoked = True
        await db.flush()


auth_service = AuthService()
