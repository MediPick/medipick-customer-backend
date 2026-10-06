"""
MediPick — Prescription Pydantic Schemas
Field names match src/api/prescriptionsApi.ts.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core import storage
from app.models.prescription import Prescription, PrescriptionStatus


class UploadUrlResponse(BaseModel):
    uploadUrl: str
    fileKey: str
    expiresIn: int


class RegisterPrescriptionBody(BaseModel):
    fileKeys: list[str] = Field(..., min_items=1)
    pharmacyId: uuid.UUID | None = None


class PrescriptionOut(BaseModel):
    id: str
    fileUrl: str
    aiClarityScore: int | None
    aiChecks: dict | None
    status: PrescriptionStatus
    pharmacistNote: str | None
    createdAt: datetime

    @staticmethod
    def from_prescription(p: Prescription) -> "PrescriptionOut":
        if p.is_purged:
            urls = ""
        else:
            urls = ",".join(storage.create_download_url(k) for k in p.file_key.split(","))
            
        return PrescriptionOut(
            id=str(p.id),
            fileUrl=urls,
            aiClarityScore=p.ai_clarity_score,
            aiChecks=p.ai_checks,
            status=p.status,
            pharmacistNote=p.pharmacist_note,
            createdAt=p.created_at,
        )


class PrescriptionStatusOut(BaseModel):
    id: str
    status: PrescriptionStatus
    aiClarityScore: int | None
