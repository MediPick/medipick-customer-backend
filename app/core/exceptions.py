"""
MediPick — Custom Exception Classes & Global HTTP Exception Handlers
All errors are wrapped in the MediPick error envelope, matching
ApiErrorResponse in src/api/client.ts:
  { "success": false, "error": "<code>", "message": "<message>", "statusCode": <int>, "fields"?: {...} }
"""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from jose import JWTError


# ─── Custom Exception ─────────────────────────────────────────────────────────

class MediPickException(Exception):
    """
    Raise this anywhere in the application to return a structured API error.
    Example:
        raise MediPickException("OTP_INVALID", 400, "The OTP you entered is incorrect.")
    """
    def __init__(self, code: str, status_code: int, message: str) -> None:
        self.code = code
        self.status_code = status_code
        self.message = message
        super().__init__(message)


# ─── Error Response Builder ───────────────────────────────────────────────────

def _error_json(code: str, message: str, status_code: int, fields: dict | None = None) -> dict:
    body: dict = {"success": False, "error": code, "message": message, "statusCode": status_code}
    if fields:
        body["fields"] = fields
    return body


# ─── Handler Registration ─────────────────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers onto the FastAPI app instance."""

    @app.exception_handler(MediPickException)
    async def medipick_exception_handler(
        request: Request, exc: MediPickException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_json(exc.code, exc.message, exc.status_code),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Flatten pydantic validation errors into the fields dict
        fields: dict[str, str] = {}
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
            fields[field] = error["msg"]

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_json(
                "VALIDATION_ERROR",
                "One or more fields failed validation.",
                status.HTTP_400_BAD_REQUEST,
                fields,
            ),
        )

    @app.exception_handler(JWTError)
    async def jwt_exception_handler(
        request: Request, exc: JWTError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=_error_json("TOKEN_INVALID", "Invalid or expired token.", status.HTTP_401_UNAUTHORIZED),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        # In dev: include the real error. In prod: hide it.
        from app.config import settings  # avoid circular import
        detail = str(exc) if settings.is_development else "An unexpected error occurred."
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_json("INTERNAL_ERROR", detail, status.HTTP_500_INTERNAL_SERVER_ERROR),
        )
