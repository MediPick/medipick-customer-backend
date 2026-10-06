"""
MediPick — Order State Machine
Every order state change goes through `transition()` so its side effects are
applied consistently no matter which feature triggered it (customer action,
pharmacist quote, payment webhook, AI prescription check, demo PATCH):

  → WAITING_CUSTOMER_CONFIRMATION  notify QUOTE_RECEIVED
  → PREPARING                      notify
  → READY_FOR_PICKUP               generate pickup code + pickup deadline, notify PICKUP_READY
  → COMPLETED                      stamp completed_at, settle pay-at-counter, notify
  → CANCELLED                      release reserved stock, refund if paid, notify ORDER_CANCELLED

Customer cancellation rules (A5.4):
  free    — before the pharmacy has committed to anything (incl. an unanswered quote)
  strike  — after the customer committed (accepted quote) or the pharmacy started preparing;
            reaching the strike limit locks the account for LOCKOUT_HOURS
  refused — once the order is at the counter or finished
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import MediPickException
from app.core.security import generate_otp
from app.core.timeutil import utcnow
from app.models.customer import Customer
from app.models.notification import NotificationType
from app.models.order import Order, OrderState, PaymentMethod
from app.models.quote import Quote, QuoteStatus
from app.services.notification_service import notification_service
from app.services.payment_service import payment_service
from app.services.stock_service import stock_service

FREE_CANCEL_STATES = {
    OrderState.DRAFT,
    OrderState.SUBMITTED,
    OrderState.PRESCRIPTION_VALIDATION,
    OrderState.AWAITING_PRESCRIPTION_UPLOAD,
    OrderState.REUPLOAD_REQUESTED,
    OrderState.WAITING_PHARMACY_CONFIRMATION,
}
TERMINAL_STATES = {OrderState.COMPLETED, OrderState.CANCELLED, OrderState.CLOSED}

_NOTIFICATIONS: dict[OrderState, tuple[NotificationType, str, str]] = {
    OrderState.WAITING_PHARMACY_CONFIRMATION: (
        NotificationType.ORDER_STATUS_CHANGED, "Sent to pharmacy",
        "Order {no} is with {pharmacy} for review.",
    ),
    OrderState.WAITING_CUSTOMER_CONFIRMATION: (
        NotificationType.QUOTE_RECEIVED, "Quote received",
        "{pharmacy} sent a price quote for order {no}. Review it before it expires.",
    ),
    OrderState.AWAITING_PRESCRIPTION_UPLOAD: (
        NotificationType.PRESCRIPTION_REJECTED, "Please re-upload your prescription",
        "The prescription for order {no} wasn't clear enough to read. Upload a sharper photo.",
    ),
    OrderState.PREPARING: (
        NotificationType.ORDER_STATUS_CHANGED, "Order is being prepared",
        "{pharmacy} is preparing order {no}.",
    ),
    OrderState.READY_FOR_PICKUP: (
        NotificationType.PICKUP_READY, "Ready for pickup",
        "Order {no} is ready at {pharmacy}. Show your pickup code at the counter.",
    ),
    OrderState.COMPLETED: (
        NotificationType.ORDER_STATUS_CHANGED, "Order completed",
        "Thanks for picking up order {no}! Tap to rate your experience.",
    ),
    OrderState.CANCELLED: (
        NotificationType.ORDER_CANCELLED, "Order cancelled",
        "Order {no} was cancelled.",
    ),
}


class OrderFSM:

    async def transition(
        self,
        db: AsyncSession,
        order: Order,
        new_state: OrderState,
        *,
        reason: str | None = None,
        notify: bool = True,
    ) -> None:
        if order.state == new_state:
            return
        now = utcnow()

        if new_state == OrderState.READY_FOR_PICKUP:
            order.pickup_code = generate_otp()
            order.pickup_code_verified = False
            order.pickup_deadline = now + timedelta(hours=settings.PICKUP_WINDOW_HOURS)
            order.pickup_extension_requested = False

        elif new_state == OrderState.COMPLETED:
            order.completed_at = now
            order.pickup_code_verified = True
            if order.payment_method != PaymentMethod.ONLINE:
                order.is_paid = True  # settled at the counter

        elif new_state == OrderState.CANCELLED:
            await stock_service.release(db, order.items)
            await db.execute(
                update(Quote)
                .where(Quote.order_id == order.id, Quote.status == QuoteStatus.PENDING)
                .values(status=QuoteStatus.EXPIRED)
            )
            if order.is_paid:
                await payment_service.refund_order(db, order)
            if reason:
                order.reject_reason = reason

        order.state = new_state
        await db.flush()

        if notify and new_state in _NOTIFICATIONS:
            ntype, title, body = _NOTIFICATIONS[new_state]
            text = body.format(no=order.order_number, pharmacy=order.pharmacy.name)
            if new_state == OrderState.CANCELLED and reason:
                text = f"{text} Reason: {reason}"
            await notification_service.notify_customer(
                db, order.customer_id, ntype, title, text, order_id=order.id,
            )

    # ── Customer-initiated cancellation (A5.4) ───────────────────────────────

    async def cancel_by_customer(self, db: AsyncSession, order: Order, customer: Customer) -> int:
        if order.state in TERMINAL_STATES or order.state not in (
            FREE_CANCEL_STATES | {OrderState.WAITING_CUSTOMER_CONFIRMATION, OrderState.PREPARING}
        ):
            raise MediPickException(
                "ORDER_NOT_CANCELLABLE", 409,
                f"Orders in state {order.state.value} can no longer be cancelled.",
            )

        if await self._customer_already_committed(db, order):
            self.apply_strike(customer)

        await self.transition(db, order, OrderState.CANCELLED, reason="Cancelled by customer")
        return customer.no_show_count

    async def _customer_already_committed(self, db: AsyncSession, order: Order) -> bool:
        if order.state == OrderState.PREPARING:
            return True
        if order.state == OrderState.WAITING_CUSTOMER_CONFIRMATION:
            accepted = await db.execute(
                select(Quote.id).where(Quote.order_id == order.id, Quote.status == QuoteStatus.ACCEPTED)
            )
            return accepted.first() is not None
        return False

    @staticmethod
    def apply_strike(customer: Customer) -> None:
        customer.no_show_count += 1
        if customer.no_show_count >= customer.strike_limit:
            customer.is_locked = True
            customer.locked_until = utcnow() + timedelta(hours=settings.LOCKOUT_HOURS)


order_fsm = OrderFSM()
