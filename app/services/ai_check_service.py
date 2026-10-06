"""
MediPick — Prescription AI Clarity Check

prescriptionsApi.ts describes the AI engine as an external pre-built service.
Until that's wired in, this local engine performs the part that can be done
honestly without ML: an image-quality check (is the photo sharp, well exposed
and high-resolution enough to read?). Replace `analyze()` with a call to the
external service later — its result shape (`AiResult`) is all the rest of the
flow depends on.

Signature / patient-name / date detection need OCR, so the local engine
reports them as not detected and leaves them to the pharmacist's review.

Runs as a background task after registration (A6.2); the client polls A6.4.
"""
from __future__ import annotations

import asyncio
import io
import logging
import math
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from app.config import settings
from app.core import storage
from app.database import AsyncSessionLocal
from app.models.order import Order, OrderState
from app.models.prescription import Prescription, PrescriptionStatus
from app.models.notification import NotificationType
from app.services.notification_service import notification_service
from app.services.order_fsm import order_fsm

logger = logging.getLogger(__name__)

# Laplacian-variance range mapped onto 0–100 (log scale). ~100 is the classic
# blurry/sharp threshold; phone photos of documents usually land well above.
_SHARPNESS_FLOOR = 20.0
_SHARPNESS_CEILING = 600.0
_MIN_READABLE_SIDE_PX = 600
# PDFs are digitally generated or already-scanned documents; pixel metrics
# don't apply, so they get a fixed "legible" score and go to the pharmacist.
_PDF_SCORE = 85


@dataclass
class AiResult:
    unreadable: bool          # not an image we can decode at all → REJECTED
    score: int | None
    checks: dict | None


def _checks(score: int) -> dict:
    return {
        "clarity": {"score": score, "max": 100, "passed": score >= settings.AI_CLARITY_PASS_SCORE},
        "doctorSignature": {"detected": False},
        "patientName": {"detected": False},
        "date": {"detected": False, "value": None},
    }


def analyze(data: bytes, content_type: str) -> AiResult:
    if content_type == "application/pdf":
        return AiResult(unreadable=False, score=_PDF_SCORE, checks=_checks(_PDF_SCORE))

    from PIL import Image, ImageFilter, ImageStat, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            gray = img.convert("L")
            gray.thumbnail((1024, 1024))  # normalise scale so scores are comparable
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return AiResult(unreadable=True, score=None, checks=None)

    laplacian = gray.filter(ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128))
    sharpness_var = ImageStat.Stat(laplacian).var[0]
    stats = ImageStat.Stat(gray)
    brightness, contrast = stats.mean[0], stats.stddev[0]

    span = math.log10(_SHARPNESS_CEILING) - math.log10(_SHARPNESS_FLOOR)
    sharp = (math.log10(max(sharpness_var, 1.0)) - math.log10(_SHARPNESS_FLOOR)) / span * 100

    penalty = 0
    if brightness < 40 or brightness > 235:
        penalty += 25   # far too dark or washed out
    if contrast < 25:
        penalty += 20   # flat — text won't stand out from paper
    if min(width, height) < _MIN_READABLE_SIDE_PX:
        penalty += 25   # too low-resolution to read small print

    score = int(max(0, min(100, round(sharp - penalty))))
    return AiResult(unreadable=False, score=score, checks=_checks(score))


async def run_ai_check(prescription_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        try:
            prescription = (await db.execute(
                select(Prescription).where(Prescription.id == prescription_id).with_for_update()
            )).scalar_one_or_none()
            if prescription is None or prescription.status != PrescriptionStatus.PRESCRIPTION_VALIDATION:
                return

            try:
                data = storage.read_file(prescription.file_key)
                result = await asyncio.to_thread(analyze, data, prescription.file_type)
            except Exception:  # noqa: BLE001
                # Fail open to human review rather than leave the customer polling forever.
                logger.exception("AI check crashed for prescription %s; routing to pharmacist", prescription_id)
                result = AiResult(unreadable=False, score=None, checks=None)

            if result.unreadable:
                new_status = PrescriptionStatus.REJECTED
            elif result.score is not None and result.score < settings.AI_CLARITY_PASS_SCORE:
                new_status = PrescriptionStatus.AWAITING_PRESCRIPTION_UPLOAD
            else:
                new_status = PrescriptionStatus.WAITING_PHARMACY_CONFIRMATION

            prescription.ai_clarity_score = result.score
            prescription.ai_checks = result.checks
            prescription.status = new_status

            linked = (await db.execute(
                select(Order)
                .where(Order.prescription_id == prescription.id, Order.state == OrderState.PRESCRIPTION_VALIDATION)
                .with_for_update()
                .execution_options(populate_existing=True)
            )).scalars().all()

            passed = new_status == PrescriptionStatus.WAITING_PHARMACY_CONFIRMATION
            for order in linked:
                if passed:
                    await order_fsm.transition(db, order, OrderState.WAITING_PHARMACY_CONFIRMATION)
                elif new_status == PrescriptionStatus.REJECTED:
                    await order_fsm.transition(
                        db, order, OrderState.CANCELLED, reason="The uploaded file isn't a readable prescription.",
                    )
                else:
                    await order_fsm.transition(db, order, OrderState.AWAITING_PRESCRIPTION_UPLOAD)

            if not passed and not linked:
                await notification_service.notify_customer(
                    db, prescription.customer_id, NotificationType.PRESCRIPTION_REJECTED,
                    "Prescription needs a clearer photo" if new_status != PrescriptionStatus.REJECTED
                    else "Prescription couldn't be read",
                    "Your prescription photo wasn't clear enough for a pharmacist to read. Please upload a sharper, "
                    "well-lit photo." if new_status != PrescriptionStatus.REJECTED
                    else "The uploaded file isn't a readable image. Please upload a photo of your prescription.",
                    prescription_id=prescription.id,
                )

            await db.commit()
        except Exception:  # noqa: BLE001
            await db.rollback()
            logger.exception("AI check failed for prescription %s", prescription_id)
