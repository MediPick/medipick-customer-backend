"""
MediPick — Signed Upload / Download Endpoints
The targets of the signed URLs issued by app/core/storage.py (stand-in for a
cloud bucket's pre-signed URLs). Authorization is the URL signature itself,
not a Bearer token — exactly like S3/GCS pre-signed URLs.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from app.config import settings
from app.core import storage
from app.core.exceptions import MediPickException
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/uploads", tags=["Uploads"])


@router.put("/{file_key:path}", response_model=SuccessResponse[dict], summary="Upload a file to a signed URL")
async def upload_file(
    file_key: str,
    request: Request,
    expires: int = Query(...),
    signature: str = Query(...),
):
    if not storage.is_valid_file_key(file_key) or not storage.verify_signature("upload", file_key, expires, signature):
        raise MediPickException("UPLOAD_URL_INVALID", 403, "This upload link is invalid or has expired.")
    if storage.file_exists(file_key):
        # Registered prescriptions/evidence must never be silently replaced.
        raise MediPickException("FILE_ALREADY_UPLOADED", 409, "A file was already uploaded to this link.")

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > settings.UPLOAD_MAX_BYTES:
            raise MediPickException(
                "FILE_TOO_LARGE", 413, f"Files can be at most {settings.UPLOAD_MAX_BYTES // (1024 * 1024)} MB.",
            )
    if not body:
        raise MediPickException("EMPTY_FILE", 400, "The uploaded file is empty.")

    data = bytes(body)
    content_type = storage.detect_content_type(data)
    if content_type not in storage.ALLOWED_CONTENT_TYPES:
        raise MediPickException("UNSUPPORTED_FILE_TYPE", 415, "Upload a JPEG, PNG, WebP image or a PDF.")

    await asyncio.to_thread(storage.save_file, file_key, data)
    return SuccessResponse(data={"fileKey": file_key, "contentType": content_type, "sizeBytes": len(data)})


@router.get("/{file_key:path}", summary="Download a file from a signed URL")
async def download_file(
    file_key: str,
    expires: int = Query(...),
    signature: str = Query(...),
):
    if not storage.is_valid_file_key(file_key) or not storage.verify_signature("download", file_key, expires, signature):
        raise MediPickException("DOWNLOAD_URL_INVALID", 403, "This link is invalid or has expired.")
    if not storage.file_exists(file_key):
        raise MediPickException("FILE_NOT_FOUND", 404, "File not found.")

    data = await asyncio.to_thread(storage.read_file, file_key)
    return Response(
        content=data,
        media_type=storage.detect_content_type(data) or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=300"},
    )
