"""
MediPick — Payments Endpoints
A8.1 needs a customer token. A8.2 is called server-to-server by the gateway
and is authenticated by its HMAC signature instead.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_customer_user
from app.core.exceptions import MediPickException
from app.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.payment import CreatePaymentIntentBody, PaymentIntentOut, WebhookAck, WebhookEvent
from app.services.payment_service import payment_service

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post(
    "/intents", status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[PaymentIntentOut], summary="A8.1 — Create payment intent",
)
async def create_payment_intent(
    body: CreatePaymentIntentBody,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=100),
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    txn = await payment_service.create_intent(db, customer, body.orderId, idempotency_key)
    return SuccessResponse(data=PaymentIntentOut(
        paymentIntentId=str(txn.id),
        clientSecret=txn.client_secret,
        amount=float(txn.amount),
        currency="LKR",
        gateway=txn.gateway,
        orderId=str(txn.order_id),
    ))


@router.post("/webhook", response_model=WebhookAck, summary="A8.2 — Gateway webhook (signed)")
async def payment_webhook(
    request: Request,
    x_medipick_signature: str | None = Header(None, alias="X-MediPick-Signature"),
    db: AsyncSession = Depends(get_db),
):
    raw_body = await request.body()
    if not payment_service.verify_signature(raw_body, x_medipick_signature):
        raise MediPickException("INVALID_SIGNATURE", 401, "Webhook signature verification failed.")
    try:
        event = WebhookEvent.model_validate_json(raw_body)
    except ValidationError:
        raise MediPickException("INVALID_WEBHOOK_PAYLOAD", 400, "Unrecognised webhook payload.")
    await payment_service.handle_webhook(db, event)
    return WebhookAck()
