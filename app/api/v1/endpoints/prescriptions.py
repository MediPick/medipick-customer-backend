"""
MediPick — Prescriptions Endpoints (A6.1 → A6.5). All require a customer token.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_customer_user
from app.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.prescription import (
    PrescriptionOut,
    PrescriptionStatusOut,
    RegisterPrescriptionBody,
    UploadUrlResponse,
)
from app.services.prescription_service import prescription_service

router = APIRouter(prefix="/prescriptions", tags=["Prescriptions"])


@router.get("/upload-url", response_model=SuccessResponse[UploadUrlResponse], summary="A6.1 — Get signed upload URL")
async def get_upload_url(current: tuple[User, Customer] = Depends(get_current_customer_user)):
    user, _ = current
    upload_url, file_key, expires_in = prescription_service.create_upload_url(user)
    return SuccessResponse(data=UploadUrlResponse(uploadUrl=upload_url, fileKey=file_key, expiresIn=expires_in))


@router.post(
    "", status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[PrescriptionOut], summary="A6.2 — Register prescription + start AI check",
)
async def register_prescription(
    body: RegisterPrescriptionBody,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    user, customer = current
    prescription = await prescription_service.register(
        db, user, customer, body.fileKeys, body.pharmacyId, background_tasks,
    )
    return SuccessResponse(data=PrescriptionOut.from_prescription(prescription))


@router.get("", response_model=SuccessResponse[list[PrescriptionOut]], summary="A6.5 — List my prescriptions")
async def list_prescriptions(
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    prescriptions = await prescription_service.list(db, customer)
    return SuccessResponse(data=[PrescriptionOut.from_prescription(p) for p in prescriptions])


@router.get("/{prescription_id}", response_model=SuccessResponse[PrescriptionOut], summary="A6.3 — Prescription detail")
async def get_prescription(
    prescription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    prescription = await prescription_service.get(db, customer, prescription_id)
    return SuccessResponse(data=PrescriptionOut.from_prescription(prescription))


@router.get(
    "/{prescription_id}/status",
    response_model=SuccessResponse[PrescriptionStatusOut], summary="A6.4 — Poll AI check status",
)
async def get_prescription_status(
    prescription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    p = await prescription_service.get(db, customer, prescription_id)
    return SuccessResponse(data=PrescriptionStatusOut(id=str(p.id), status=p.status, aiClarityScore=p.ai_clarity_score))
