"""
MediPick — Message Service (order chat, A9)
The customer who owns the order and pharmacy-side roles can read and post.
New messages are also pushed live to everyone subscribed to the order over
the WebSocket (A13.1, see app/core/realtime.py).

Staff roles aren't yet tied to a specific pharmacy (the PHARMACY_STAFF domain
doesn't exist), so any pharmacist can reach any order's chat for now.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import realtime
from app.core.exceptions import MediPickException
from app.models.chat import ChatMessage, ChatSession, SenderRole
from app.models.customer import Customer
from app.models.order import Order, OrderState
from app.models.user import User, UserRole
from app.schemas.message import ChatMessageOut

STAFF_ROLES = {UserRole.PHARMACIST, UserRole.PHARMACY_STAFF, UserRole.PLATFORM_ADMIN}
CLOSED_CHAT_STATES = {OrderState.CANCELLED, OrderState.CLOSED}


class MessageService:

    async def _authorized_order(self, db: AsyncSession, user: User, order_id: uuid.UUID) -> tuple[Order, Customer | None]:
        order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
        if order is None:
            raise MediPickException("ORDER_NOT_FOUND", 404, "Order not found.")
        if user.role in STAFF_ROLES:
            return order, None
        customer = (await db.execute(select(Customer).where(Customer.user_id == user.id))).scalar_one_or_none()
        if customer is None or order.customer_id != customer.id:
            raise MediPickException("ORDER_NOT_FOUND", 404, "Order not found.")
        return order, customer

    async def can_access(self, db: AsyncSession, user_id: uuid.UUID, order_id: uuid.UUID) -> bool:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None or not user.is_active:
            return False
        try:
            await self._authorized_order(db, user, order_id)
        except MediPickException:
            return False
        return True

    async def _session_for(self, db: AsyncSession, order: Order) -> ChatSession:
        # ON CONFLICT so two first messages racing each other can't create two sessions.
        await db.execute(
            insert(ChatSession)
            .values(id=uuid.uuid4(), order_id=order.id, customer_id=order.customer_id, pharmacy_id=order.pharmacy_id)
            .on_conflict_do_nothing(index_elements=["order_id"])
        )
        return (await db.execute(select(ChatSession).where(ChatSession.order_id == order.id))).scalar_one()

    # ── A9.1 ──────────────────────────────────────────────────────────────────

    async def list_messages(self, db: AsyncSession, user: User, order_id: uuid.UUID) -> list[ChatMessageOut]:
        order, _ = await self._authorized_order(db, user, order_id)
        session = (await db.execute(select(ChatSession).where(ChatSession.order_id == order.id))).scalar_one_or_none()
        if session is None:
            return []
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.chat_session_id == session.id)
            .order_by(ChatMessage.sent_at.asc(), ChatMessage.id.asc())
        )
        return [ChatMessageOut.from_message(m, order.id) for m in result.scalars().all()]

    # ── A9.2 ──────────────────────────────────────────────────────────────────

    async def send(self, db: AsyncSession, user: User, order_id: uuid.UUID, text: str) -> ChatMessageOut:
        order, customer = await self._authorized_order(db, user, order_id)
        if order.state in CLOSED_CHAT_STATES:
            raise MediPickException("CHAT_CLOSED", 409, "This order's chat is closed.")

        role = SenderRole(user.role.value)
        if customer is not None:
            sender_name = customer.username
        elif role == SenderRole.PHARMACIST:
            sender_name = order.pharmacy.pharmacist_name or "Pharmacist"
        elif role == SenderRole.PHARMACY_STAFF:
            sender_name = "Pharmacy Staff"
        else:
            sender_name = "MediPick Support"

        session = await self._session_for(db, order)
        message = ChatMessage(
            chat_session_id=session.id,
            sender_role=role,
            sender_user_id=user.id,
            sender_name=sender_name,
            message_body=text.strip(),
        )
        db.add(message)
        await db.flush()
        out = ChatMessageOut.from_message(message, order.id)

        # Commit before broadcasting so nobody receives a message that could still roll back.
        await db.commit()
        await realtime.emit_new_message(order.id, out.model_dump(mode="json"))
        return out


message_service = MessageService()
