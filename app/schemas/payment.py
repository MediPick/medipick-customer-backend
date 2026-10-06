"""
MediPick — Payment Pydantic Schemas
Field names match src/api/paymentsApi.ts.
"""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel


class CreatePaymentIntentBody(BaseModel):
    orderId: uuid.UUID
    paymentMethod: Literal["ONLINE"]


class PaymentIntentOut(BaseModel):
    paymentIntentId: str
    clientSecret: str
    amount: float
    currency: Literal["LKR"]
    gateway: str
    orderId: str


class WebhookEventData(BaseModel):
    intentId: str


class WebhookEvent(BaseModel):
    """Gateway-agnostic webhook payload (the mock gateway sends this shape;
    a real gateway adapter would translate its own event into it)."""
    type: Literal["payment_intent.succeeded", "payment_intent.payment_failed"]
    data: WebhookEventData


class WebhookAck(BaseModel):
    received: bool = True
