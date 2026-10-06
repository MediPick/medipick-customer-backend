"""
MediPick — Quote Service
A7 (customer: view / accept / decline) plus the pharmacist-side quote creation
that feeds it.

Accepting a quote makes it the order's source of truth: the order's items and
totals are replaced by the quoted ones. If the same prescription was sent to
several pharmacies (SelectPharmacyScreen), accepting one pharmacy's quote
cancels the other still-open orders for that prescription — otherwise several
pharmacies would end up preparing the same prescription.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import MediPickException
from app.core.timeutil import as_aware, utcnow
from app.models.customer import Customer
from app.models.medicine import Medicine
from app.models.notification import NotificationType
from app.models.order import Order, OrderItem, OrderState, PaymentMethod
from app.models.quote import Quote, QuoteItem, QuoteStatus
from app.models.user import User
from app.schemas.quote import CreateQuoteBody
from app.services.notification_service import notification_service
from app.services.order_fsm import FREE_CANCEL_STATES, order_fsm
from app.services.order_service import order_service
from app.services.payment_service import payment_service
from app.services.stock_service import stock_service

QUOTABLE_STATES = {
    OrderState.PRESCRIPTION_VALIDATION,
    OrderState.WAITING_PHARMACY_CONFIRMATION,
    OrderState.WAITING_CUSTOMER_CONFIRMATION,  # re-quote supersedes the pending one
}


class QuoteService:

    async def _latest_quote(self, db: AsyncSession, order_id: uuid.UUID) -> Quote | None:
        result = await db.execute(
            select(Quote)
            .where(Quote.order_id == order_id)
            .order_by(Quote.created_at.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def _expire_if_stale(self, db: AsyncSession, quote: Quote, order: Order) -> None:
        if quote.status != QuoteStatus.PENDING or as_aware(quote.valid_until) > utcnow():
            return
        quote.status = QuoteStatus.EXPIRED
        if order.state == OrderState.WAITING_CUSTOMER_CONFIRMATION:
            order.sla_customer_confirm_deadline = None
            await order_fsm.transition(db, order, OrderState.WAITING_PHARMACY_CONFIRMATION, notify=False)
        await db.flush()

    async def _pending_quote_for_customer(
        self, db: AsyncSession, customer: Customer, order_id: uuid.UUID
    ) -> tuple[Order, Quote]:
        order = await order_service.load_order(db, order_id, customer_id=customer.id, for_update=True)
        quote = await self._latest_quote(db, order.id)
        if quote is None:
            raise MediPickException("QUOTE_NOT_FOUND", 404, "The pharmacy hasn't sent a quote for this order yet.")
        await self._expire_if_stale(db, quote, order)
        if quote.status == QuoteStatus.EXPIRED:
            raise MediPickException("QUOTE_EXPIRED", 409, "This quote has expired. The pharmacy can send a new one.")
        if quote.status != QuoteStatus.PENDING:
            raise MediPickException("QUOTE_NOT_PENDING", 409, f"This quote was already {quote.status.value.lower()}.")
        return order, quote

    # ── A7.1 — Current quote ─────────────────────────────────────────────────

    async def get_current_quote(self, db: AsyncSession, customer: Customer, order_id: uuid.UUID) -> Quote:
        order = await order_service.load_order(db, order_id, customer_id=customer.id)
        quote = await self._latest_quote(db, order.id)
        if quote is None:
            raise MediPickException("QUOTE_NOT_FOUND", 404, "The pharmacy hasn't sent a quote for this order yet.")
        await self._expire_if_stale(db, quote, order)
        return await self._latest_quote(db, order.id)

    # ── A7.2 — Accept ─────────────────────────────────────────────────────────

    async def accept(
        self, db: AsyncSession, customer: Customer, order_id: uuid.UUID
    ) -> tuple[Order, str | None]:
        order, quote = await self._pending_quote_for_customer(db, customer, order_id)
        quote.status = QuoteStatus.ACCEPTED
        quote.responded_at = utcnow()

        # The quote becomes the order: swap items, re-reserving stock where tracked.
        await stock_service.release(db, order.items)
        order.items.clear()
        await db.flush()

        images = await self._medicine_images(db, [i.medicine_id for i in quote.items if i.medicine_id])
        for qi in quote.items:
            item = OrderItem(
                line_no=qi.line_no,
                medicine_id=qi.medicine_id,
                medicine_name=qi.medicine_name,
                generic_name=qi.generic_name,
                dosage=qi.dosage,
                image=images.get(qi.medicine_id),
                quantity=qi.quantity,
                unit_mrp=float(qi.mrp),
                unit_price=float(qi.quoted_price),
                is_generic_substitute=qi.is_alternative,
                original_prescribed=qi.original_prescribed,
            )
            await stock_service.try_reserve(db, order.pharmacy_id, item)
            order.items.append(item)
        order.total_amount = float(quote.total_amount)
        order.total_mrp = float(quote.total_mrp)
        order.sla_customer_confirm_deadline = None
        await db.flush()

        client_secret = None
        if order.payment_method == PaymentMethod.ONLINE:
            # Stays WAITING_CUSTOMER_CONFIRMATION until the payment webhook lands.
            txn = await payment_service.intent_for_accepted_quote(db, order)
            client_secret = txn.client_secret
            
            from app.config import settings
            if settings.is_development:
                # Mock: Skip the webhook in development and just mark it paid and advance it
                order.is_paid = True
                await order_fsm.transition(db, order, OrderState.PREPARING)
        else:
            if order.payment_method is None:
                order.payment_method = PaymentMethod.PAY_AT_COUNTER
            await order_fsm.transition(db, order, OrderState.PREPARING)

        await self._cancel_sibling_orders(db, order)
        return await order_service.load_order(db, order.id), client_secret

    async def _cancel_sibling_orders(self, db: AsyncSession, chosen: Order) -> None:
        if chosen.prescription_id is None:
            return
        result = await db.execute(
            select(Order)
            .where(
                Order.prescription_id == chosen.prescription_id,
                Order.customer_id == chosen.customer_id,
                Order.id != chosen.id,
                Order.state.in_(FREE_CANCEL_STATES | {OrderState.WAITING_CUSTOMER_CONFIRMATION}),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        for sibling in result.scalars().all():
            await order_fsm.transition(
                db, sibling, OrderState.CANCELLED,
                reason=f"You chose {chosen.pharmacy.name} for this prescription.",
            )

    @staticmethod
    async def _medicine_images(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, str | None]:
        if not ids:
            return {}
        result = await db.execute(select(Medicine.id, Medicine.image).where(Medicine.id.in_(ids)))
        return {mid: image for mid, image in result.all()}

    # ── A7.3 — Decline ────────────────────────────────────────────────────────

    async def decline(self, db: AsyncSession, customer: Customer, order_id: uuid.UUID) -> None:
        order, quote = await self._pending_quote_for_customer(db, customer, order_id)
        quote.status = QuoteStatus.DECLINED
        quote.responded_at = utcnow()
        order.sla_customer_confirm_deadline = None
        # Back to the pharmacy, which may send a revised quote.
        await order_fsm.transition(db, order, OrderState.WAITING_PHARMACY_CONFIRMATION, notify=False)
        await db.flush()

    # ── Pharmacist: create quote ─────────────────────────────────────────────

    async def create_quote(
        self, db: AsyncSession, staff: User, order_id: uuid.UUID, body: CreateQuoteBody
    ) -> Quote:
        order = await order_service.load_order(db, order_id, for_update=True)
        if order.state not in QUOTABLE_STATES:
            raise MediPickException("ORDER_NOT_QUOTABLE", 409, f"Orders in state {order.state.value} can't be quoted.")

        await db.execute(
            update(Quote)
            .where(Quote.order_id == order.id, Quote.status == QuoteStatus.PENDING)
            .values(status=QuoteStatus.EXPIRED)
        )

        catalog_ids = [i.medicineId for i in body.items if i.medicineId]
        catalog: dict[uuid.UUID, Medicine] = {}
        if catalog_ids:
            result = await db.execute(select(Medicine).where(Medicine.id.in_(catalog_ids)))
            catalog = {m.id: m for m in result.scalars().all()}
            missing = [str(i) for i in catalog_ids if i not in catalog]
            if missing:
                raise MediPickException("MEDICINE_NOT_FOUND", 404, f"Unknown medicine id(s): {', '.join(missing)}.")

        items = []
        for line_no, spec in enumerate(body.items, start=1):
            medicine = catalog.get(spec.medicineId) if spec.medicineId else None
            items.append(QuoteItem(
                line_no=line_no,
                medicine_id=spec.medicineId,
                medicine_name=spec.medicineName or medicine.name,
                generic_name=spec.genericName or (medicine.generic_name if medicine else None),
                dosage=spec.dosage or (medicine.strength if medicine else None),
                quantity=spec.quantity,
                mrp=spec.mrp if spec.mrp is not None else float(medicine.mrp_price),
                quoted_price=spec.quotedPrice,
                is_alternative=spec.isAlternative,
                original_prescribed=spec.originalPrescribed,
            ))

        valid_until = utcnow() + timedelta(minutes=body.validMinutes or settings.QUOTE_VALID_MINUTES)
        quote = Quote(
            order_id=order.id,
            pharmacy_id=order.pharmacy_id,
            created_by_user_id=staff.id,
            status=QuoteStatus.PENDING,
            total_amount=round(sum(float(i.quoted_price) * i.quantity for i in items), 2),
            total_mrp=round(sum(float(i.mrp) * i.quantity for i in items), 2),
            valid_until=valid_until,
        )
        quote.items = items
        db.add(quote)
        order.sla_customer_confirm_deadline = valid_until

        if order.state == OrderState.WAITING_CUSTOMER_CONFIRMATION:
            await notification_service.notify_customer(
                db, order.customer_id, NotificationType.QUOTE_RECEIVED, "Revised quote received",
                f"{order.pharmacy.name} sent an updated quote for order {order.order_number}.",
                order_id=order.id,
            )
        else:
            await order_fsm.transition(db, order, OrderState.WAITING_CUSTOMER_CONFIRMATION)
        await db.flush()
        return await self._latest_quote(db, order.id)


quote_service = QuoteService()
