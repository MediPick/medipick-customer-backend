"""
MediPick — Order Pydantic Schemas
Field names match src/api/ordersApi.ts. A few extra fields (`item.price`,
`prescriptionUri`) are included because screens read them directly
(OrderDetailsScreen) even though the typed contract doesn't declare them.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core import storage
from app.models.order import Order, OrderItem, OrderState, OrderType, PaymentMethod

# Pickup code is only meaningful (and only shown) once the order is at the counter.
_PICKUP_CODE_VISIBLE_STATES = {OrderState.READY_FOR_PICKUP}


class OrderMedicineOut(BaseModel):
    name: str
    genericName: str | None
    dosage: str | None
    image: str | None


class OrderItemOut(BaseModel):
    id: str
    medicineId: str | None
    medicine: OrderMedicineOut
    quantity: int
    unitMrp: float
    unitPrice: float
    price: float
    lineTotal: float
    isSubstitute: bool
    originalPrescribed: str | None

    @staticmethod
    def from_item(item: OrderItem) -> "OrderItemOut":
        unit_price = float(item.unit_price)
        return OrderItemOut(
            id=str(item.id),
            medicineId=str(item.medicine_id) if item.medicine_id else None,
            medicine=OrderMedicineOut(
                name=item.medicine_name,
                genericName=item.generic_name,
                dosage=item.dosage,
                image=item.image,
            ),
            quantity=item.quantity,
            unitMrp=float(item.unit_mrp),
            unitPrice=unit_price,
            price=unit_price,
            lineTotal=round(unit_price * item.quantity, 2),
            isSubstitute=item.is_generic_substitute,
            originalPrescribed=item.original_prescribed,
        )


class OrderPharmacyOut(BaseModel):
    id: str
    name: str
    address: str
    image: str | None
    nmraLicense: str
    pharmacistName: str
    estimatedResponseTime: str


class OrderRatingOut(BaseModel):
    overall: int
    service: int
    availability: int
    pickup: int
    comment: str | None


class OrderOut(BaseModel):
    """Matches the client's `Order` interface (a superset of `OrderSummary`,
    so the list endpoint returns this too — OrderContext treats list rows as
    full orders)."""
    id: str
    orderNumber: str
    orderType: OrderType
    state: OrderState
    pharmacy: OrderPharmacyOut
    prescriptionId: str | None
    prescriptionUri: str | None
    items: list[OrderItemOut]
    itemCount: int
    totalMrp: float
    totalAmount: float
    savings: float
    paymentMethod: PaymentMethod | None
    isPaid: bool
    allowGenericSubstitutions: bool
    rejectReason: str | None
    refundStatus: str | None
    customerNote: str | None
    pickupOtp: str | None
    pickupOtpVerified: bool
    rating: OrderRatingOut | None
    pickupDeadline: datetime | None
    pickupExtensionRequested: bool
    slaPharmacyReviewDeadline: datetime | None
    slaCustomerConfirmDeadline: datetime | None
    createdAt: datetime
    updatedAt: datetime

    @staticmethod
    def from_order(order: Order) -> "OrderOut":
        pharmacy = order.pharmacy
        total_mrp = float(order.total_mrp)
        total_amount = float(order.total_amount)
        prescription = order.prescription
        rating = order.rating
        return OrderOut(
            id=str(order.id),
            orderNumber=order.order_number,
            orderType=order.order_type,
            state=order.state,
            pharmacy=OrderPharmacyOut(
                id=str(pharmacy.id),
                name=pharmacy.name,
                address=pharmacy.address or "",
                image=pharmacy.image,
                nmraLicense=pharmacy.nmra_license or "",
                pharmacistName=pharmacy.pharmacist_name or "",
                estimatedResponseTime=pharmacy.estimated_response_time,
            ),
            prescriptionId=str(order.prescription_id) if order.prescription_id else None,
            prescriptionUri=(
                storage.create_download_url(prescription.file_key)
                if prescription is not None and not prescription.is_purged
                else None
            ),
            items=[OrderItemOut.from_item(i) for i in order.items],
            itemCount=sum(i.quantity for i in order.items),
            totalMrp=total_mrp,
            totalAmount=total_amount,
            savings=round(max(total_mrp - total_amount, 0), 2),
            paymentMethod=order.payment_method,
            isPaid=order.is_paid,
            allowGenericSubstitutions=order.allow_generic_substitution,
            rejectReason=order.reject_reason,
            refundStatus=order.refund_status,
            customerNote=order.customer_note,
            pickupOtp=order.pickup_code if order.state in _PICKUP_CODE_VISIBLE_STATES else None,
            pickupOtpVerified=order.pickup_code_verified,
            rating=(
                OrderRatingOut(
                    overall=rating.overall_rating,
                    service=rating.service_rating,
                    availability=rating.availability_rating,
                    pickup=rating.pickup_rating,
                    comment=rating.comment,
                )
                if rating is not None
                else None
            ),
            pickupDeadline=order.pickup_deadline,
            pickupExtensionRequested=order.pickup_extension_requested,
            slaPharmacyReviewDeadline=order.sla_pharmacy_review_deadline,
            slaCustomerConfirmDeadline=order.sla_customer_confirm_deadline,
            createdAt=order.created_at,
            updatedAt=order.updated_at,
        )


# ─── A5.3 — Create order ──────────────────────────────────────────────────────

class CreateOrderItem(BaseModel):
    medicineId: uuid.UUID
    quantity: int = Field(..., ge=1, le=99)


class CreateOrderBody(BaseModel):
    orderType: OrderType
    pharmacyId: uuid.UUID
    items: list[CreateOrderItem] = Field(default_factory=list, max_length=50)
    paymentMethod: PaymentMethod | None = None
    allowGenericSubstitutions: bool = False
    prescriptionId: uuid.UUID | None = None
    customerNote: str | None = Field(None, max_length=500)


# ─── A5.4 — Cancel ────────────────────────────────────────────────────────────

class CancelOrderResponse(BaseModel):
    message: str
    strikes: int


# ─── A5.6 — Rating ────────────────────────────────────────────────────────────

class RatingBreakdown(BaseModel):
    overall: int = Field(..., ge=1, le=5)
    service: int = Field(..., ge=1, le=5)
    availability: int = Field(..., ge=1, le=5)
    pickup: int = Field(..., ge=1, le=5)


class SubmitRatingBody(BaseModel):
    """ordersApi.ts types `rating` as a number, but RateExperienceScreen sends
    the full breakdown object — accept both."""
    rating: int | RatingBreakdown = Field(...)
    comment: str | None = Field(None, max_length=1000)

    @field_validator("rating")
    @classmethod
    def _rating_in_range(cls, v: int | RatingBreakdown) -> int | RatingBreakdown:
        if isinstance(v, int) and not 1 <= v <= 5:
            raise ValueError("rating must be between 1 and 5")
        return v

    def breakdown(self) -> RatingBreakdown:
        if isinstance(self.rating, RatingBreakdown):
            return self.rating
        r = self.rating
        return RatingBreakdown(overall=r, service=r, availability=r, pickup=r)


# ─── A5.7 — Pickup extension ─────────────────────────────────────────────────

class PickupExtensionResponse(BaseModel):
    message: str
    newDeadline: datetime


# ─── A5.8 — Update Payment Method ─────────────────────────────────────────────

class UpdatePaymentMethodBody(BaseModel):
    paymentMethod: PaymentMethod

# ─── Demo-only state change (PATCH /orders/{id}) ─────────────────────────────

class UpdateOrderStateBody(BaseModel):
    state: OrderState
