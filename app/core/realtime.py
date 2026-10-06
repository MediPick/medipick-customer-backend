"""
MediPick — Real-time (Socket.IO) — A13.1

websocketApi.ts connects with socket.io-client to `API_BASE_URL` with http→ws,
i.e. ws://<host>/api/v1. Socket.IO treats that URL path as the *namespace*
(the transport path stays the default /socket.io/), so the server listens on
namespace "/api/v1".

Handshake: auth = { token: "Bearer <access token>" }, query = { orderId }.
The socket joins the room for that order if the caller may see its chat, and
receives `new_message` events (ChatMessageOut shape) as they're posted.
"""
from __future__ import annotations

import logging
import uuid
from urllib.parse import parse_qs

import socketio
from jose import JWTError
# Must be Socket.IO's own exception (it shadows the builtin): only this one is
# turned into a proper `connect_error` packet for the client.
from socketio.exceptions import ConnectionRefusedError

from app.config import settings
from app.core.security import decode_access_token
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

NAMESPACE = "/api/v1"

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*" if "*" in settings.CORS_ORIGINS else settings.CORS_ORIGINS,
)


def order_room(order_id: uuid.UUID) -> str:
    return f"order:{order_id}"


async def emit_new_message(order_id: uuid.UUID, payload: dict) -> None:
    await sio.emit("new_message", payload, room=order_room(order_id), namespace=NAMESPACE)


class OrderChatNamespace(socketio.AsyncNamespace):

    async def on_connect(self, sid, environ, auth=None):
        from app.services.message_service import message_service  # local import: it imports this module

        token = str((auth or {}).get("token", "")).removeprefix("Bearer ").strip()
        order_id_raw = parse_qs(environ.get("QUERY_STRING", "")).get("orderId", [""])[0]
        try:
            payload = decode_access_token(token)
            user_id = uuid.UUID(payload["sub"])
            order_id = uuid.UUID(order_id_raw)
        except (JWTError, KeyError, ValueError):
            raise ConnectionRefusedError("unauthorized")

        async with AsyncSessionLocal() as db:
            allowed = await message_service.can_access(db, user_id, order_id)
        if not allowed:
            raise ConnectionRefusedError("unauthorized")

        await self.enter_room(sid, order_room(order_id))
        logger.info("socket %s joined %s", sid, order_room(order_id))

    async def on_disconnect(self, sid):
        logger.info("socket %s disconnected", sid)


sio.register_namespace(OrderChatNamespace(NAMESPACE))
