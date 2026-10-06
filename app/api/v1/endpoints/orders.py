"""
MediPick — Orders Endpoints (A5.1 → A5.7, plus the demo state PATCH that
OrderContext uses). All require a customer token.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_customer_user
from app.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.common import MessageResponse, PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.order import (
    CancelOrderResponse,
    CreateOrderBody,
    OrderOut,
    PickupExtensionResponse,
    SubmitRatingBody,
    UpdateOrderStateBody,
    UpdatePaymentMethodBody,
)
from app.services.order_service import order_service

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("", response_model=PaginatedResponse[list[OrderOut]], summary="A5.1 — List my orders")
async def list_orders(
    state: str | None = Query(None, description="Comma-separated states, e.g. PREPARING,READY_FOR_PICKUP"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    orders, total = await order_service.list_orders(db, customer.id, state, page, limit)
    return PaginatedResponse(
        data=[OrderOut.from_order(o) for o in orders],
        meta=PaginationMeta.build(page, limit, total),
    )


@router.post(
    "", status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[OrderOut], summary="A5.3 — Create order",
)
async def create_order(
    body: CreateOrderBody,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=100),
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    order = await order_service.create_order(db, customer, body, idempotency_key=idempotency_key)
    return SuccessResponse(data=OrderOut.from_order(order))


@router.get("/{order_id}", response_model=SuccessResponse[OrderOut], summary="A5.2 — Order detail")
async def get_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    order = await order_service.load_order(db, order_id, customer_id=customer.id)
    return SuccessResponse(data=OrderOut.from_order(order))


@router.patch(
    "/{order_id}", response_model=SuccessResponse[OrderOut],
    summary="Demo — set order state (cancel/issue always; any state in development)",
)
async def update_order_state(
    order_id: uuid.UUID,
    body: UpdateOrderStateBody,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    order = await order_service.set_state(db, customer, order_id, body.state)
    return SuccessResponse(data=OrderOut.from_order(order))


@router.post("/{order_id}/cancel", response_model=SuccessResponse[CancelOrderResponse], summary="A5.4 — Cancel order")
async def cancel_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    strikes = await order_service.cancel_order(db, customer, order_id)
    return SuccessResponse(data=CancelOrderResponse(message="Order cancelled.", strikes=strikes))


@router.post(
    "/{order_id}/reorder", status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[OrderOut], summary="A5.5 — Reorder",
)
async def reorder(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    order = await order_service.reorder(db, customer, order_id)
    return SuccessResponse(data=OrderOut.from_order(order))


@router.post(
    "/{order_id}/ratings", status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[MessageResponse], summary="A5.6 — Rate order",
)
async def submit_rating(
    order_id: uuid.UUID,
    body: SubmitRatingBody,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    await order_service.submit_rating(db, customer, order_id, body)
    return SuccessResponse(data=MessageResponse(message="Thanks for your feedback!"))


@router.post(
    "/{order_id}/pickup/extension-requests",
    response_model=SuccessResponse[PickupExtensionResponse], summary="A5.7 — Extend pickup deadline",
)
async def request_pickup_extension(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    new_deadline = await order_service.request_pickup_extension(db, customer, order_id)
    return SuccessResponse(data=PickupExtensionResponse(message="Pickup deadline extended.", newDeadline=new_deadline))


@router.patch(
    "/{order_id}/payment-method", response_model=SuccessResponse[OrderOut],
    summary="A5.8 — Update payment method",
)
async def update_payment_method(
    order_id: uuid.UUID,
    body: UpdatePaymentMethodBody,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    order = await order_service.update_payment_method(db, customer, order_id, body.paymentMethod)
    return SuccessResponse(data=OrderOut.from_order(order))
