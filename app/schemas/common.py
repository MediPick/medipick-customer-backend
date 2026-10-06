"""
MediPick — Common Pydantic Schemas
The unified API response envelope used by every endpoint.
Matches the frontend client.ts ApiSuccessResponse / ApiErrorResponse types.
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class SuccessResponse(BaseModel, Generic[DataT]):
    """
    Standard success envelope.
    Frontend expects: { success: true, data: T, meta?: { page, limit, total, totalPages } }
    """
    success: bool = True
    data: DataT


class MessageResponse(BaseModel):
    """For actions whose only result is a human-readable confirmation."""
    message: str


class PaginationMeta(BaseModel):
    page: int
    limit: int
    total: int
    totalPages: int

    @staticmethod
    def build(page: int, limit: int, total: int) -> "PaginationMeta":
        return PaginationMeta(page=page, limit=limit, total=total, totalPages=(total + limit - 1) // limit)


class PaginatedResponse(BaseModel, Generic[DataT]):
    success: bool = True
    data: DataT
    meta: PaginationMeta


class ErrorResponse(BaseModel):
    """
    Standard error envelope. Matches ApiErrorResponse in src/api/client.ts:
    { success: false, error: "<code>", message: "<message>", statusCode: <int> }
    """
    success: bool = False
    error: str
    message: str
    statusCode: int
    fields: dict[str, str] | None = None
