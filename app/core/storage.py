"""
MediPick — File Storage (local disk + HMAC-signed URLs)

Mimics cloud storage pre-signed URLs (what src/api/prescriptionsApi.ts expects):
the client gets a short-lived signed PUT URL, uploads the file straight to it,
then passes the returned `fileKey` back to the API. Downloads use signed GET
URLs too, since prescriptions are medical data and must never be public.

Swapping to S3/GCS later only means reimplementing the functions in this
module — callers only deal in `file_key`s and URLs.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode

from app.config import settings

_BACKEND_ROOT = Path(__file__).resolve().parents[2]

# purpose/<user uuid>/<random hex> — strict so a key can never escape UPLOAD_DIR.
_FILE_KEY_RE = re.compile(r"^[a-z_]+/[0-9a-f-]{36}/[0-9a-f]{32}$")

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


def _upload_root() -> Path:
    root = Path(settings.UPLOAD_DIR)
    return root if root.is_absolute() else _BACKEND_ROOT / root


def make_file_key(purpose: str, owner_user_id: uuid.UUID) -> str:
    return f"{purpose}/{owner_user_id}/{uuid.uuid4().hex}"


def is_valid_file_key(file_key: str) -> bool:
    return bool(_FILE_KEY_RE.match(file_key))


def owner_id_from_key(file_key: str) -> str:
    return file_key.split("/")[1]


def _signature(action: str, file_key: str, expires: int) -> str:
    message = f"{action}:{file_key}:{expires}".encode()
    return hmac.new(settings.JWT_SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def _signed_url(action: str, file_key: str, ttl_seconds: int) -> str:
    expires = int(time.time()) + ttl_seconds
    query = urlencode({"expires": expires, "signature": _signature(action, file_key, expires)})
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/api/v1/uploads/{file_key}?{query}"


def create_upload_url(file_key: str) -> str:
    return _signed_url("upload", file_key, settings.UPLOAD_URL_EXPIRE_SECONDS)


def create_download_url(file_key: str) -> str:
    return _signed_url("download", file_key, settings.DOWNLOAD_URL_EXPIRE_SECONDS)


def verify_signature(action: str, file_key: str, expires: int, signature: str) -> bool:
    if expires < int(time.time()):
        return False
    return hmac.compare_digest(_signature(action, file_key, expires), signature)


def detect_content_type(data: bytes) -> str | None:
    """Sniff the real file type from magic bytes — never trust the client's Content-Type."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF"):
        return "application/pdf"
    return None


def _path_for(file_key: str) -> Path:
    return _upload_root() / file_key


def save_file(file_key: str, data: bytes) -> None:
    path = _path_for(file_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def file_exists(file_key: str) -> bool:
    return is_valid_file_key(file_key) and _path_for(file_key).is_file()


def read_file(file_key: str) -> bytes:
    return _path_for(file_key).read_bytes()


def file_size(file_key: str) -> int:
    return _path_for(file_key).stat().st_size
