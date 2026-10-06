"""
MediPick — Quote Pydantic Schemas
Field names match src/api/quotesApi.ts.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.quote import Quote, QuoteStatus


class QuoteItemOut(BaseModel):
    id: str
    medicineId: str | None
    medicineName: str
    genericName: str | None
    quantity: int
    mrp: float
    quotedPrice: float
    lineTotal: float
    isAlternative: bool
    originalPrescribed: str | None


class QuoteOut(BaseModel):
    id: str
    orderId: str
    pharmacyName: str
    pharmacistName: str
    nmraLicense: str
    items: list[QuoteItemOut]
    totalAmount: float
    totalMrp: float
    savings: float
    status: QuoteStatus
    validUntil: datetime
    createdAt: datetime

    @staticmethod
    def from_quote(q: Quote) -> "QuoteOut":
        total_amount = float(q.total_amount)
        total_mrp = float(q.total_mrp)
        return QuoteOut(
            id=str(q.id),
            orderId=str(q.order_id),
            pharmacyName=q.pharmacy.name,
            pharmacistName=q.pharmacy.pharmacist_name or "",
            nmraLicense=q.pharmacy.nmra_license or "",
            items=[
                QuoteItemOut(
                    id=str(i.id),
                    medicineId=str(i.medicine_id) if i.medicine_id else None,
                    medicineName=i.medicine_name,
                    genericName=i.generic_name,
                    quantity=i.quantity,
                    mrp=float(i.mrp),
                    quotedPrice=float(i.quoted_price),
                    lineTotal=round(float(i.quoted_price) * i.quantity, 2),
                    isAlternative=i.is_alternative,
                    originalPrescribed=i.original_prescribed,
                )
                for i in q.items
            ],
            totalAmount=total_amount,
            totalMrp=total_mrp,
            savings=round(max(total_mrp - total_amount, 0), 2),
            status=q.status,
            validUntil=q.valid_until,
            createdAt=q.created_at,
        )


class AcceptQuoteOrderRef(BaseModel):
    id: str
    state: str


class AcceptQuoteResponse(BaseModel):
    message: str
    order: AcceptQuoteOrderRef
    paymentClientSecret: str | None = None


# ─── Pharmacist-side: create a quote ─────────────────────────────────────────

class CreateQuoteItem(BaseModel):
    """Either reference a catalog medicine (name/mrp are filled from it) or
    describe a free-text item the catalog doesn't have."""
    medicineId: uuid.UUID | None = None
    medicineName: str | None = Field(None, max_length=255)
    genericName: str | None = Field(None, max_length=255)
    dosage: str | None = Field(None, max_length=100)
    quantity: int = Field(..., ge=1, le=99)
    mrp: float | None = Field(None, ge=0)
    quotedPrice: float = Field(..., ge=0)
    isAlternative: bool = False
    originalPrescribed: str | None = Field(None, max_length=255)

    @model_validator(mode="after")
    def _needs_identity(self) -> "CreateQuoteItem":
        if self.medicineId is None and (not self.medicineName or self.mrp is None):
            raise ValueError("Provide medicineId, or both medicineName and mrp for a non-catalog item.")
        return self


class CreateQuoteBody(BaseModel):
    items: list[CreateQuoteItem] = Field(..., min_length=1, max_length=50)
    validMinutes: int | None = Field(None, ge=5, le=24 * 60)
