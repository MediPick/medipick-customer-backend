"""
MediPick — Notification Pydantic Schemas
Field names match src/api/notificationsApi.ts (note: `read`, not `isRead`).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.notification import Notification, NotificationType


class NotificationOut(BaseModel):
    id: str
    type: NotificationType
    title: str
    body: str
    orderId: str | None
    read: bool
    createdAt: datetime

    @staticmethod
    def from_notification(n: Notification) -> "NotificationOut":
        return NotificationOut(
            id=str(n.id),
            type=n.notification_type,
            title=n.title,
            body=n.message_body,
            orderId=str(n.order_id) if n.order_id else None,
            read=n.is_read,
            createdAt=n.created_at,
        )


class MarkReadBody(BaseModel):
    read: bool = True


class MarkReadResponse(BaseModel):
    id: str
    read: bool


class MarkAllReadResponse(BaseModel):
    markedCount: int
