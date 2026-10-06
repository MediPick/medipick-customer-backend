"""
MediPick — Order Chat Endpoints (A9.1 → A9.2)
Open to the order's customer and pharmacy-side roles; the sender role comes
from the token, never from the request body.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.message import ChatMessageOut, SendMessageBody
from app.services.message_service import message_service

router = APIRouter(prefix="/orders", tags=["Messages"])


@router.get("/{order_id}/messages", response_model=SuccessResponse[list[ChatMessageOut]], summary="A9.1 — Chat history")
async def get_messages(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return SuccessResponse(data=await message_service.list_messages(db, user, order_id))


@router.post(
    "/{order_id}/messages", status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[ChatMessageOut], summary="A9.2 — Send a message",
)
async def send_message(
    order_id: uuid.UUID,
    body: SendMessageBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return SuccessResponse(data=await message_service.send(db, user, order_id, body.text))
