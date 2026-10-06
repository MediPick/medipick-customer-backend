"""
MediPick — Quotes Endpoints
A7.1 → A7.3 are customer actions. Quote creation is pharmacist-side (the
contract: "Only PHARMACIST can CREATE a quote").
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_customer_user, require_roles
from app.database import get_db
from app.models.customer import Customer
from app.models.user import User, UserRole
from app.schemas.common import MessageResponse, SuccessResponse
from app.schemas.quote import AcceptQuoteOrderRef, AcceptQuoteResponse, CreateQuoteBody, QuoteOut
from app.services.quote_service import quote_service

router = APIRouter(prefix="/orders", tags=["Quotes"])

_quote_authors = require_roles(UserRole.PHARMACIST, UserRole.PHARMACY_STAFF, UserRole.PLATFORM_ADMIN)


@router.get("/{order_id}/quotes/current", response_model=SuccessResponse[QuoteOut], summary="A7.1 — Current quote")
async def get_current_quote(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    quote = await quote_service.get_current_quote(db, customer, order_id)
    return SuccessResponse(data=QuoteOut.from_quote(quote))


@router.post(
    "/{order_id}/quotes/current/accept",
    response_model=SuccessResponse[AcceptQuoteResponse], response_model_exclude_none=True,
    summary="A7.2 — Accept quote",
)
async def accept_quote(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    order, client_secret = await quote_service.accept(db, customer, order_id)
    return SuccessResponse(data=AcceptQuoteResponse(
        message="Quote accepted." if client_secret is None else "Quote accepted — complete payment to confirm.",
        order=AcceptQuoteOrderRef(id=str(order.id), state=order.state.value),
        paymentClientSecret=client_secret,
    ))


@router.post(
    "/{order_id}/quotes/current/decline",
    response_model=SuccessResponse[MessageResponse], summary="A7.3 — Decline quote",
)
async def decline_quote(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    await quote_service.decline(db, customer, order_id)
    return SuccessResponse(data=MessageResponse(message="Quote declined. The pharmacy may send a revised quote."))


@router.post(
    "/{order_id}/quotes", status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[QuoteOut], summary="Pharmacist — send a quote",
)
async def create_quote(
    order_id: uuid.UUID,
    body: CreateQuoteBody,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(_quote_authors),
):
    quote = await quote_service.create_quote(db, staff, order_id, body)
    return SuccessResponse(data=QuoteOut.from_quote(quote))
