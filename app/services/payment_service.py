"""
MediPick — Payment Service
Creates payment intents (A8.1) and processes the gateway webhook (A8.2).

Gateways are pluggable. Only a `mock` gateway ships today — it issues fake
intent IDs / client secrets and never moves money. A real adapter (e.g.
PayHere, which serves Sri Lankan merchants) implements the same two methods
and translates its webhook into our `WebhookEvent`; nothing else changes.

Webhooks are authenticated with an HMAC-SHA256 signature over the raw body:
    X-MediPick-Signature: sha256=<hex digest using PAYMENT_WEBHOOK_SECRET>
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import MediPickException
from app.models.customer import Customer
from app.models.notification import NotificationType
from app.models.order import Order, OrderState, PaymentMethod
from app.models.payment import PaymentStatus, PaymentTransaction
from app.models.quote import Quote, QuoteStatus
from app.schemas.payment import WebhookEvent
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)

PAYABLE_STATES = {
    OrderState.SUBMITTED,
    OrderState.WAITING_PHARMACY_CONFIRMATION,
    OrderState.WAITING_CUSTOMER_CONFIRMATION,
    OrderState.PREPARING,
    OrderState.READY_FOR_PICKUP,
}


class MockPaymentGateway:
    name = "mock"

    def create_intent(self, amount: float, currency: str, reference: str) -> tuple[str, str]:
        intent_id = f"pi_mock_{uuid.uuid4().hex[:24]}"
        return intent_id, f"{intent_id}_secret_{secrets.token_urlsafe(16)}"

    def refund(self, intent_id: str, amount: float) -> None:
        logger.info("[mock gateway] refunded %s LKR on %s", amount, intent_id)


def _build_gateway():
    if settings.PAYMENT_GATEWAY == "mock":
        return MockPaymentGateway()
    raise RuntimeError(f"Unknown PAYMENT_GATEWAY '{settings.PAYMENT_GATEWAY}'")


class PaymentService:

    def __init__(self) -> None:
        self.gateway = _build_gateway()

    # ── Create intent (A8.1) ─────────────────────────────────────────────────

    async def create_intent(
        self,
        db: AsyncSession,
        customer: Customer,
        order_id: uuid.UUID,
        idempotency_key: str | None,
    ) -> PaymentTransaction:
        if idempotency_key:
            existing = await db.execute(
                select(PaymentTransaction).where(
                    PaymentTransaction.customer_id == customer.id,
                    PaymentTransaction.idempotency_key == idempotency_key,
                )
            )
            replay = existing.scalar_one_or_none()
            if replay is not None:
                return replay

        result = await db.execute(
            select(Order).where(Order.id == order_id, Order.customer_id == customer.id).with_for_update()
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise MediPickException("ORDER_NOT_FOUND", 404, "Order not found.")

        pending_quote = await db.execute(
            select(Quote.id).where(Quote.order_id == order.id, Quote.status == QuoteStatus.PENDING)
        )
        if pending_quote.first() is not None:
            raise MediPickException(
                "QUOTE_PENDING", 409, "Accept the pharmacy's quote before paying for this order."
            )

        return await self._intent_for_order(db, order, idempotency_key)

    async def _intent_for_order(
        self, db: AsyncSession, order: Order, idempotency_key: str | None = None
    ) -> PaymentTransaction:
        if order.is_paid:
            raise MediPickException("ORDER_ALREADY_PAID", 409, "This order has already been paid.")
        if order.state not in PAYABLE_STATES:
            raise MediPickException(
                "ORDER_NOT_PAYABLE", 409, f"Orders in state {order.state.value} can't be paid."
            )
        amount = float(order.total_amount)
        if amount <= 0:
            raise MediPickException(
                "ORDER_NOT_PAYABLE", 409, "This order has no price yet — wait for the pharmacy's quote."
            )

        # Reopening the pay screen shouldn't create a new intent every time.
        pending = await db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.order_id == order.id,
                PaymentTransaction.status == PaymentStatus.PENDING,
            )
        )
        for txn in pending.scalars().all():
            if float(txn.amount) == amount:
                return txn
            txn.status = PaymentStatus.FAILED  # amount changed (e.g. new quote) — retire it

        intent_id, client_secret = self.gateway.create_intent(amount, "LKR", order.order_number)
        txn = PaymentTransaction(
            order_id=order.id,
            customer_id=order.customer_id,
            gateway=self.gateway.name,
            gateway_intent_id=intent_id,
            client_secret=client_secret,
            status=PaymentStatus.PENDING,
            amount=amount,
            currency="LKR",
            idempotency_key=idempotency_key,
        )
        db.add(txn)
        order.payment_method = PaymentMethod.ONLINE
        await db.flush()
        return txn

    async def intent_for_accepted_quote(self, db: AsyncSession, order: Order) -> PaymentTransaction:
        """Used by quote acceptance for ONLINE orders."""
        return await self._intent_for_order(db, order)

    # ── Webhook (A8.2) ───────────────────────────────────────────────────────

    @staticmethod
    def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = hmac.new(settings.PAYMENT_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))

    async def handle_webhook(self, db: AsyncSession, event: WebhookEvent) -> None:
        from app.services.order_fsm import order_fsm  # local import: order_fsm imports this module

        result = await db.execute(
            select(PaymentTransaction)
            .where(PaymentTransaction.gateway_intent_id == event.data.intentId)
            .with_for_update()
        )
        txn = result.scalar_one_or_none()
        if txn is None:
            logger.warning("Webhook for unknown payment intent %s ignored", event.data.intentId)
            return

        order_result = await db.execute(select(Order).where(Order.id == txn.order_id).with_for_update())
        order = order_result.scalar_one()

        if event.type == "payment_intent.payment_failed":
            if txn.status == PaymentStatus.PENDING:
                txn.status = PaymentStatus.FAILED
                await notification_service.notify_customer(
                    db, order.customer_id, NotificationType.SYSTEM,
                    "Payment failed",
                    f"Your payment for order {order.order_number} didn't go through. Please try again.",
                    order_id=order.id,
                )
            return

        # payment_intent.succeeded — gateways can deliver the same event twice.
        if txn.status in (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED):
            return
        txn.status = PaymentStatus.SUCCEEDED

        if order.state == OrderState.CANCELLED:
            # Customer cancelled while the payment was in flight — give it straight back.
            await self._refund_transactions(db, order, [txn])
            return

        order.is_paid = True
        order.payment_method = PaymentMethod.ONLINE
        await notification_service.notify_customer(
            db, order.customer_id, NotificationType.PAYMENT_CONFIRMED,
            "Payment confirmed",
            f"We received LKR {float(txn.amount):,.2f} for order {order.order_number}.",
            order_id=order.id,
        )
        # An accepted quote waits in WAITING_CUSTOMER_CONFIRMATION until paid.
        if order.state == OrderState.WAITING_CUSTOMER_CONFIRMATION:
            await order_fsm.transition(db, order, OrderState.PREPARING)
        await db.flush()

    # ── Refunds (on cancellation) ────────────────────────────────────────────

    async def refund_order(self, db: AsyncSession, order: Order) -> None:
        result = await db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.order_id == order.id,
                PaymentTransaction.status == PaymentStatus.SUCCEEDED,
            )
        )
        await self._refund_transactions(db, order, list(result.scalars().all()))

    async def _refund_transactions(
        self, db: AsyncSession, order: Order, txns: list[PaymentTransaction]
    ) -> None:
        refunded = 0.0
        for txn in txns:
            self.gateway.refund(txn.gateway_intent_id, float(txn.amount))
            txn.status = PaymentStatus.REFUNDED
            refunded += float(txn.amount)
        if refunded > 0:
            order.refund_status = "REFUNDED"
            order.refund_amount = refunded
        await db.flush()


payment_service = PaymentService()
