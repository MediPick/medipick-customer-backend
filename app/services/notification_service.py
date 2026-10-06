"""
MediPick — Notification Service
Creates in-app notifications (A10) and, when the customer has registered an
Expo push token (A2.6) and left push enabled, also delivers a push notification
through Expo's push service (free, no account or API key needed).

Push delivery is fire-and-forget: a slow or failing push must never fail the
request that triggered it.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import MediPickException
from app.models.customer import Customer
from app.models.notification import Notification, NotificationType

logger = logging.getLogger(__name__)

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

# Holds strong references so in-flight push tasks aren't garbage-collected.
_background_pushes: set[asyncio.Task] = set()


async def _send_expo_push(token: str, title: str, body: str, data: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                _EXPO_PUSH_URL,
                json={"to": token, "title": title, "body": body, "data": data, "sound": "default"},
            )
            if resp.status_code >= 400:
                logger.warning("Expo push rejected (%s): %s", resp.status_code, resp.text[:200])
    except Exception:  # noqa: BLE001 — push is best-effort by design
        logger.warning("Expo push failed", exc_info=True)


class NotificationService:

    # ── Create ────────────────────────────────────────────────────────────────

    async def notify_customer(
        self,
        db: AsyncSession,
        customer_id: uuid.UUID,
        notification_type: NotificationType,
        title: str,
        body: str,
        order_id: uuid.UUID | None = None,
        prescription_id: uuid.UUID | None = None,
    ) -> Notification | None:
        result = await db.execute(select(Customer).where(Customer.id == customer_id))
        customer = result.scalar_one_or_none()
        if customer is None:
            return None

        notification = Notification(
            user_id=customer.user_id,
            order_id=order_id,
            prescription_id=prescription_id,
            notification_type=notification_type,
            title=title,
            message_body=body,
        )
        db.add(notification)
        await db.flush()

        if settings.EXPO_PUSH_ENABLED and customer.push_notifications_enabled and customer.push_token:
            data = {"type": notification_type.value, "notificationId": str(notification.id)}
            if order_id:
                data["orderId"] = str(order_id)
            task = asyncio.create_task(_send_expo_push(customer.push_token, title, body, data))
            _background_pushes.add(task)
            task.add_done_callback(_background_pushes.discard)

        return notification

    # ── List (A10.1) ──────────────────────────────────────────────────────────

    async def list_notifications(
        self, db: AsyncSession, user_id: uuid.UUID, unread_only: bool, page: int, limit: int
    ) -> tuple[list[Notification], int]:
        conditions = [Notification.user_id == user_id]
        if unread_only:
            conditions.append(Notification.is_read.is_(False))

        total = (await db.execute(select(func.count()).select_from(Notification).where(*conditions))).scalar_one()
        result = await db.execute(
            select(Notification)
            .where(*conditions)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    # ── Mark one (A10.2) ─────────────────────────────────────────────────────

    async def set_read(
        self, db: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID, read: bool
    ) -> Notification:
        result = await db.execute(
            select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
        )
        notification = result.scalar_one_or_none()
        if notification is None:
            raise MediPickException("NOTIFICATION_NOT_FOUND", 404, "Notification not found.")
        notification.is_read = read
        await db.flush()
        return notification

    # ── Mark all (A10.3) ─────────────────────────────────────────────────────

    async def mark_all_read(self, db: AsyncSession, user_id: uuid.UUID) -> int:
        result = await db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True)
        )
        return result.rowcount or 0


notification_service = NotificationService()
