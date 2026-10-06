"""
MediPick — Prescription Service
A6 upload flow:
  1. create_upload_url()  → signed PUT URL + fileKey          (A6.1)
  2. client PUTs the image to that URL (uploads endpoint)
  3. register()           → row created, AI check scheduled   (A6.2)
  4. client polls status until it leaves PRESCRIPTION_VALIDATION (A6.4)
"""
from __future__ import annotations

import uuid

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import storage
from app.core.exceptions import MediPickException
from app.models.customer import Customer
from app.models.pharmacy import Pharmacy
from app.models.prescription import Prescription, PrescriptionStatus
from app.models.user import User
from app.services.ai_check_service import run_ai_check

UPLOAD_PURPOSE = "prescriptions"


class PrescriptionService:

    # ── A6.1 ──────────────────────────────────────────────────────────────────

    def create_upload_url(self, user: User) -> tuple[str, str, int]:
        file_key = storage.make_file_key(UPLOAD_PURPOSE, user.id)
        return storage.create_upload_url(file_key), file_key, settings.UPLOAD_URL_EXPIRE_SECONDS

    # ── A6.2 ──────────────────────────────────────────────────────────────────

    async def register(
        self,
        db: AsyncSession,
        user: User,
        customer: Customer,
        file_keys: list[str],
        pharmacy_id: uuid.UUID | None,
        background_tasks: BackgroundTasks,
    ) -> Prescription:
        for file_key in file_keys:
            if (
                not storage.is_valid_file_key(file_key)
                or not file_key.startswith(f"{UPLOAD_PURPOSE}/")
                or storage.owner_id_from_key(file_key) != str(user.id)
            ):
                raise MediPickException("INVALID_FILE_KEY", 400, "That file key wasn't issued to you.")
            if not storage.file_exists(file_key):
                raise MediPickException("FILE_NOT_UPLOADED", 400, "Upload the file to the upload URL first.")

        # Just check the first one for existing to avoid complex array queries
        existing = (await db.execute(select(Prescription).where(Prescription.file_key == file_keys[0]))).scalar_one_or_none()
        if existing is not None:
            return existing  # re-registering the same upload is a harmless retry

        if pharmacy_id is not None:
            if (await db.execute(select(Pharmacy.id).where(Pharmacy.id == pharmacy_id))).first() is None:
                raise MediPickException("PHARMACY_NOT_FOUND", 404, "Pharmacy not found.")

        # Primary file for backward compatibility
        primary_key = file_keys[0]
        data = storage.read_file(primary_key)
        
        prescription = Prescription(
            customer_id=customer.id,
            pharmacy_id=pharmacy_id,
            file_key=primary_key,
            file_keys=file_keys,
            file_type=storage.detect_content_type(data) or "application/octet-stream",
            file_size_bytes=sum(len(storage.read_file(fk)) for fk in file_keys),
            status=PrescriptionStatus.PRESCRIPTION_VALIDATION,
        )
        db.add(prescription)
        await db.flush()
        # Commit now (not at request end) so the background AI check — which
        # uses its own session — is guaranteed to see this row.
        await db.commit()
        background_tasks.add_task(run_ai_check, prescription.id)
        return prescription

    # ── A6.3 / A6.4 ───────────────────────────────────────────────────────────

    async def get(self, db: AsyncSession, customer: Customer, prescription_id: uuid.UUID) -> Prescription:
        result = await db.execute(
            select(Prescription)
            .where(Prescription.id == prescription_id, Prescription.customer_id == customer.id)
            .execution_options(populate_existing=True)
        )
        prescription = result.scalar_one_or_none()
        if prescription is None:
            raise MediPickException("PRESCRIPTION_NOT_FOUND", 404, "Prescription not found.")
        return prescription

    # ── A6.5 ──────────────────────────────────────────────────────────────────

    async def list(self, db: AsyncSession, customer: Customer) -> list[Prescription]:
        result = await db.execute(
            select(Prescription)
            .where(Prescription.customer_id == customer.id)
            .order_by(Prescription.created_at.desc())
        )
        return list(result.scalars().all())


prescription_service = PrescriptionService()
