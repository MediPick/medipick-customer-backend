"""
MediPick — Order Service
Business logic for A5 (orders). State changes are delegated to order_fsm so
their side effects stay consistent.

Always return orders via `load_order()`: it re-SELECTs with populate_existing,
which refreshes columns the DB changed on flush (e.g. updated_at) — reading an
expired attribute on an async session would otherwise trigger implicit IO.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import MediPickException
from app.core.timeutil import as_aware, utcnow
from app.models.customer import Customer
from app.models.medicine import Medicine
from app.models.notification import NotificationType
from app.models.order import Order, OrderItem, OrderRating, OrderState, OrderType
from app.models.pharmacy import Pharmacy, PharmacyStatus
from app.models.prescription import Prescription, PrescriptionStatus
from app.schemas.order import CreateOrderBody, CreateOrderItem, SubmitRatingBody
from app.services.notification_service import notification_service
from app.services.order_fsm import order_fsm
from app.services.stock_service import stock_service


class OrderService:

    # ── Loading ───────────────────────────────────────────────────────────────

    async def load_order(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        *,
        customer_id: uuid.UUID | None = None,
        for_update: bool = False,
    ) -> Order:
        query = select(Order).where(Order.id == order_id).execution_options(populate_existing=True)
        if customer_id is not None:
            query = query.where(Order.customer_id == customer_id)
        if for_update:
            query = query.with_for_update()
        order = (await db.execute(query)).scalar_one_or_none()
        if order is None:
            raise MediPickException("ORDER_NOT_FOUND", 404, "Order not found.")
        return order

    # ── List (A5.1) ───────────────────────────────────────────────────────────

    async def list_orders(
        self, db: AsyncSession, customer_id: uuid.UUID, state_filter: str | None, page: int, limit: int
    ) -> tuple[list[Order], int]:
        conditions = [Order.customer_id == customer_id]
        if state_filter:
            try:
                states = [OrderState(s.strip()) for s in state_filter.split(",") if s.strip()]
            except ValueError:
                raise MediPickException("INVALID_STATE_FILTER", 400, f"Unknown order state in '{state_filter}'.")
            if states:
                conditions.append(Order.state.in_(states))

        total = (await db.execute(select(func.count()).select_from(Order).where(*conditions))).scalar_one()
        result = await db.execute(
            select(Order)
            .where(*conditions)
            .order_by(Order.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    # ── Create (A5.3) ─────────────────────────────────────────────────────────

    async def create_order(
        self,
        db: AsyncSession,
        customer: Customer,
        body: CreateOrderBody,
        *,
        idempotency_key: str | None = None,
        original_order_id: uuid.UUID | None = None,
    ) -> Order:
        if idempotency_key:
            replay = await db.execute(
                select(Order.id).where(Order.customer_id == customer.id, Order.idempotency_key == idempotency_key)
            )
            replay_id = replay.scalar_one_or_none()
            if replay_id is not None:
                return await self.load_order(db, replay_id)

        self._ensure_can_order(customer)

        pharmacy = (await db.execute(select(Pharmacy).where(Pharmacy.id == body.pharmacyId))).scalar_one_or_none()
        if pharmacy is None:
            raise MediPickException("PHARMACY_NOT_FOUND", 404, "Pharmacy not found.")
        if pharmacy.status != PharmacyStatus.APPROVED:
            raise MediPickException("PHARMACY_UNAVAILABLE", 409, f"{pharmacy.name} isn't accepting orders.")

        prescription = await self._validated_prescription(db, customer, body.prescriptionId)
        self._validate_type(body, prescription)

        lines = self._merge_lines(body.items)
        medicines = await self._load_medicines(db, list(lines))

        if prescription is None:
            rx_only = [m.name for m in medicines.values() if m.requires_prescription]
            if rx_only:
                raise MediPickException(
                    "PRESCRIPTION_REQUIRED", 400,
                    f"A prescription is required for: {', '.join(rx_only)}.",
                )

        items, problems = [], []
        for line_no, (medicine_id, quantity) in enumerate(lines.items(), start=1):
            medicine = medicines[medicine_id]
            inventory = await stock_service.lock_inventory(db, pharmacy.id, medicine_id)
            if inventory is None:
                problems.append(f"{medicine.name} (not sold here)")
                continue
            if inventory.stock_quantity < quantity:
                problems.append(f"{medicine.name} (only {inventory.stock_quantity} left)")
                continue
            inventory.stock_quantity -= quantity
            items.append(OrderItem(
                line_no=line_no,
                medicine_id=medicine.id,
                inventory_item_id=inventory.id,
                medicine_name=medicine.name,
                generic_name=medicine.generic_name,
                dosage=medicine.strength,
                image=medicine.image,
                quantity=quantity,
                unit_mrp=float(medicine.mrp_price),
                unit_price=float(inventory.unit_price),
            ))
        if problems:
            # Raising rolls back the whole transaction, including stock already decremented above.
            raise MediPickException(
                "OUT_OF_STOCK", 409, f"{pharmacy.name} can't fill: {'; '.join(problems)}.",
            )

        now = utcnow()
        initial_state = OrderState.WAITING_PHARMACY_CONFIRMATION
        if prescription is not None and prescription.status == PrescriptionStatus.PRESCRIPTION_VALIDATION:
            initial_state = OrderState.PRESCRIPTION_VALIDATION
        elif body.orderType == OrderType.OTC:
            initial_state = OrderState.PREPARING
        order = Order(
            order_number=await self._new_order_number(db),
            customer_id=customer.id,
            pharmacy_id=pharmacy.id,
            prescription_id=prescription.id if prescription else None,
            original_order_id=original_order_id,
            order_type=body.orderType,
            state=initial_state,
            payment_method=body.paymentMethod,
            total_mrp=round(sum(float(i.unit_mrp) * i.quantity for i in items), 2),
            total_amount=round(sum(float(i.unit_price) * i.quantity for i in items), 2),
            allow_generic_substitution=body.allowGenericSubstitutions,
            customer_note=body.customerNote,
            sla_pharmacy_review_deadline=now + timedelta(minutes=settings.ORDER_PHARMACY_REVIEW_SLA_MINUTES),
            idempotency_key=idempotency_key,
        )
        order.items = items
        db.add(order)
        await db.flush()

        body_text = (
            f"We're checking your prescription for order {order.order_number}."
            if initial_state == OrderState.PRESCRIPTION_VALIDATION
            else f"Order {order.order_number} was sent to {pharmacy.name}."
        )
        await notification_service.notify_customer(
            db, customer.id, NotificationType.ORDER_STATUS_CHANGED, "Order placed", body_text, order_id=order.id,
        )
        return await self.load_order(db, order.id)

    def _ensure_can_order(self, customer: Customer) -> None:
        if not customer.is_locked:
            return
        if customer.locked_until is not None and as_aware(customer.locked_until) > utcnow():
            raise MediPickException(
                "ACCOUNT_LOCKED", 403,
                "Ordering is paused on your account after repeated cancellations. "
                f"Try again after {as_aware(customer.locked_until).strftime('%Y-%m-%d %H:%M UTC')}.",
            )
        # Lockout served — start with a clean slate.
        customer.is_locked = False
        customer.locked_until = None
        customer.no_show_count = 0

    async def _validated_prescription(
        self, db: AsyncSession, customer: Customer, prescription_id: uuid.UUID | None
    ) -> Prescription | None:
        if prescription_id is None:
            return None
        # Locked so a concurrently finishing AI check either sees this order
        # (and advances it) or has already updated the status we read here.
        prescription = (await db.execute(
            select(Prescription)
            .where(Prescription.id == prescription_id, Prescription.customer_id == customer.id)
            .with_for_update()
        )).scalar_one_or_none()
        if prescription is None:
            raise MediPickException("PRESCRIPTION_NOT_FOUND", 404, "Prescription not found.")
        if prescription.status == PrescriptionStatus.REJECTED:
            raise MediPickException("PRESCRIPTION_REJECTED", 409, "This prescription was rejected. Upload a new one.")
        if prescription.status == PrescriptionStatus.AWAITING_PRESCRIPTION_UPLOAD:
            raise MediPickException(
                "PRESCRIPTION_REUPLOAD_REQUIRED", 409, "This prescription wasn't clear enough. Upload a new photo.",
            )
        return prescription

    @staticmethod
    def _validate_type(body: CreateOrderBody, prescription: Prescription | None) -> None:
        if body.orderType in (OrderType.PRESCRIPTION, OrderType.MIXED) and prescription is None:
            raise MediPickException("PRESCRIPTION_REQUIRED", 400, f"{body.orderType.value} orders need a prescriptionId.")
        if body.orderType in (OrderType.OTC, OrderType.MIXED) and not body.items:
            raise MediPickException("ITEMS_REQUIRED", 400, f"{body.orderType.value} orders need at least one item.")

    @staticmethod
    def _merge_lines(items: list[CreateOrderItem]) -> dict[uuid.UUID, int]:
        lines: dict[uuid.UUID, int] = {}
        for item in items:
            lines[item.medicineId] = lines.get(item.medicineId, 0) + item.quantity
        return lines

    @staticmethod
    async def _load_medicines(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, Medicine]:
        if not ids:
            return {}
        result = await db.execute(select(Medicine).where(Medicine.id.in_(ids)))
        medicines = {m.id: m for m in result.scalars().all()}
        missing = [str(i) for i in ids if i not in medicines]
        if missing:
            raise MediPickException("MEDICINE_NOT_FOUND", 404, f"Unknown medicine id(s): {', '.join(missing)}.")
        return medicines

    @staticmethod
    async def _new_order_number(db: AsyncSession) -> str:
        for _ in range(10):
            candidate = f"#MP{secrets.randbelow(900000) + 100000}"
            taken = await db.execute(select(Order.id).where(Order.order_number == candidate))
            if taken.first() is None:
                return candidate
        raise MediPickException("ORDER_NUMBER_EXHAUSTED", 500, "Couldn't allocate an order number. Please retry.")

    # ── Cancel (A5.4) ─────────────────────────────────────────────────────────

    async def cancel_order(self, db: AsyncSession, customer: Customer, order_id: uuid.UUID) -> int:
        order = await self.load_order(db, order_id, customer_id=customer.id, for_update=True)
        return await order_fsm.cancel_by_customer(db, order, customer)

    # ── Reorder (A5.5) ────────────────────────────────────────────────────────

    async def reorder(self, db: AsyncSession, customer: Customer, order_id: uuid.UUID) -> Order:
        old = await self.load_order(db, order_id, customer_id=customer.id)
        if old.state not in (OrderState.COMPLETED, OrderState.CANCELLED):
            raise MediPickException("ORDER_NOT_REORDERABLE", 409, "Only completed or cancelled orders can be reordered.")

        catalog_items = [
            CreateOrderItem(medicineId=i.medicine_id, quantity=i.quantity) for i in old.items if i.medicine_id
        ]
        order_type = old.order_type
        if order_type == OrderType.PRESCRIPTION:
            catalog_items = []  # the pharmacy re-quotes against the prescription
        elif order_type == OrderType.MIXED and not catalog_items:
            order_type = OrderType.PRESCRIPTION
        elif order_type == OrderType.OTC and not catalog_items:
            raise MediPickException(
                "ORDER_NOT_REORDERABLE", 409, "None of this order's medicines are in the catalog anymore.",
            )

        body = CreateOrderBody(
            orderType=order_type,
            pharmacyId=old.pharmacy_id,
            items=catalog_items,
            paymentMethod=old.payment_method,
            allowGenericSubstitutions=old.allow_generic_substitution,
            prescriptionId=old.prescription_id,
            customerNote=old.customer_note,
        )
        return await self.create_order(db, customer, body, original_order_id=old.id)

    # ── Rating (A5.6) ─────────────────────────────────────────────────────────

    async def submit_rating(
        self, db: AsyncSession, customer: Customer, order_id: uuid.UUID, body: SubmitRatingBody
    ) -> None:
        order = await self.load_order(db, order_id, customer_id=customer.id, for_update=True)
        if order.completed_at is None:
            raise MediPickException("ORDER_NOT_COMPLETED", 409, "You can rate an order once you've picked it up.")
        if order.rating is not None:
            raise MediPickException("ALREADY_RATED", 409, "You've already rated this order.")

        scores = body.breakdown()
        db.add(OrderRating(
            order_id=order.id,
            customer_id=customer.id,
            pharmacy_id=order.pharmacy_id,
            overall_rating=scores.overall,
            service_rating=scores.service,
            availability_rating=scores.availability,
            pickup_rating=scores.pickup,
            comment=body.comment or None,
        ))
        # Atomic increment so concurrent ratings can't lose updates.
        await db.execute(
            update(Pharmacy)
            .where(Pharmacy.id == order.pharmacy_id)
            .values(
                rating_total=Pharmacy.rating_total + scores.overall,
                rating_count=Pharmacy.rating_count + 1,
            )
        )
        await db.flush()

    # ── Pickup extension (A5.7) ───────────────────────────────────────────────

    async def request_pickup_extension(
        self, db: AsyncSession, customer: Customer, order_id: uuid.UUID
    ) -> datetime:
        order = await self.load_order(db, order_id, customer_id=customer.id, for_update=True)
        if order.state != OrderState.READY_FOR_PICKUP:
            raise MediPickException("ORDER_NOT_READY", 409, "Only orders ready for pickup can be extended.")
        if order.pickup_extension_requested:
            raise MediPickException("EXTENSION_ALREADY_USED", 409, "This order's pickup has already been extended once.")

        base = as_aware(order.pickup_deadline) if order.pickup_deadline else utcnow()
        order.pickup_deadline = base + timedelta(hours=settings.PICKUP_EXTENSION_HOURS)
        order.pickup_extension_requested = True
        await db.flush()
        return order.pickup_deadline

    # ── Demo-only direct state change (PATCH /orders/{id}) ──────────────────

    async def set_state(
        self, db: AsyncSession, customer: Customer, order_id: uuid.UUID, new_state: OrderState
    ) -> Order:
        """
        OrderContext uses this for "complete", "cancel" and "report issue".
        Cancellation always goes through the real cancel rules. Any other jump
        is only allowed in development, except flagging an issue on a
        completed order, which is a legitimate customer action.
        """
        order = await self.load_order(db, order_id, customer_id=customer.id, for_update=True)

        if new_state == OrderState.CANCELLED:
            await order_fsm.cancel_by_customer(db, order, customer)
        elif new_state == OrderState.ISSUE_REPORTED and order.state == OrderState.COMPLETED:
            await order_fsm.transition(db, order, new_state)
        elif settings.is_development:
            if new_state == OrderState.WAITING_CUSTOMER_CONFIRMATION and order.state != OrderState.WAITING_CUSTOMER_CONFIRMATION:
                from datetime import timedelta
                from app.models.quote import Quote, QuoteItem, QuoteStatus
                from app.core.timeutil import utcnow
                from sqlalchemy import update
                
                # Expire old quotes first
                await db.execute(
                    update(Quote)
                    .where(Quote.order_id == order.id, Quote.status == QuoteStatus.PENDING)
                    .values(status=QuoteStatus.EXPIRED)
                )

                valid_until = utcnow() + timedelta(hours=24)
                items = []
                line_no = 1
                
                # Preserve existing items (e.g. OTC items requested by customer)
                for order_item in order.items:
                    items.append(
                        QuoteItem(
                            line_no=line_no,
                            medicine_id=order_item.medicine_id,
                            medicine_name=order_item.medicine_name,
                            generic_name=order_item.generic_name,
                            dosage=order_item.dosage,
                            quantity=order_item.quantity,
                            mrp=float(order_item.unit_mrp),
                            quoted_price=float(order_item.unit_price) * 0.95 if order_item.unit_price else float(order_item.unit_mrp), # 5% discount
                            original_prescribed=order_item.original_prescribed
                        )
                    )
                    line_no += 1
                
                # Simulate pharmacist adding prescribed items from the image
                if order.prescription_id:
                    items.extend([
                        QuoteItem(
                            line_no=line_no,
                            medicine_name="Amoxicillin 500mg",
                            quantity=20,
                            mrp=15.0,
                            quoted_price=12.0,
                        ),
                        QuoteItem(
                            line_no=line_no + 1,
                            medicine_name="Panadol 500mg",
                            quantity=10,
                            mrp=5.0,
                            quoted_price=4.5,
                            is_alternative=True,
                            original_prescribed="Paracetamol 500mg"
                        )
                    ])
                quote = Quote(
                    order_id=order.id,
                    pharmacy_id=order.pharmacy_id,
                    status=QuoteStatus.PENDING,
                    total_amount=round(sum(float(i.quoted_price) * i.quantity for i in items), 2),
                    total_mrp=round(sum(float(i.mrp) * i.quantity for i in items), 2),
                    valid_until=valid_until,
                )
                quote.items = items
                db.add(quote)
                order.sla_customer_confirm_deadline = valid_until

            await order_fsm.transition(db, order, new_state)
        else:
            raise MediPickException(
                "FORBIDDEN", 403, "Direct order state changes are only available in development.",
            )
        return await self.load_order(db, order.id)


    async def update_payment_method(
        self, db: AsyncSession, customer: Customer, order_id: uuid.UUID, payment_method: PaymentMethod
    ) -> Order:
        order = await self.load_order(db, order_id, customer_id=customer.id, for_update=True)
        if order.is_paid:
            raise MediPickException("ALREADY_PAID", 409, "Cannot change payment method because the order is already paid.")
        
        # Ensure we're not modifying cancelled or completed orders
        if order.state in (OrderState.CANCELLED, OrderState.COMPLETED, OrderState.ISSUE_REPORTED):
            raise MediPickException("INVALID_STATE", 409, "Cannot change payment method for this order state.")

        order.payment_method = payment_method
        await db.flush()
        return await self.load_order(db, order.id)

order_service = OrderService()
