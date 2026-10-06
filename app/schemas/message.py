"""
MediPick — Chat Message Pydantic Schemas
Field names match src/api/messagesApi.ts. The same shape is pushed over the
WebSocket as the `new_message` event.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.timeutil import format_local_clock
from app.models.chat import ChatMessage, SenderRole


class ChatMessageOut(BaseModel):
    id: str
    orderId: str
    senderRole: SenderRole
    senderName: str
    text: str
    timestamp: str
    createdAt: datetime

    @staticmethod
    def from_message(m: ChatMessage, order_id: uuid.UUID) -> "ChatMessageOut":
        return ChatMessageOut(
            id=str(m.id),
            orderId=str(order_id),
            senderRole=m.sender_role,
            senderName=m.sender_name,
            text=m.message_body,
            timestamp=format_local_clock(m.sent_at),
            createdAt=m.sent_at,
        )


class SendMessageBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
