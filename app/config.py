"""
MediPick Backend — Configuration
Loads all settings from environment variables / .env file.
"""
from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql+asyncpg://medipick:password@localhost:5432/medipick_db"
    )

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── OTP ───────────────────────────────────────────────────────────────────
    OTP_EXPIRE_MINUTES: int = 5
    OTP_RATE_LIMIT: int = 3       # max OTP requests per phone per 10 minutes
    OTP_MAX_ATTEMPTS: int = 5     # max wrong OTP entries before lockout

    # ── Strike / Lockout ──────────────────────────────────────────────────────
    STRIKE_LIMIT: int = 5
    LOCKOUT_HOURS: int = 1

    # ── Orders / Quotes / Pickup ──────────────────────────────────────────────
    ORDER_PHARMACY_REVIEW_SLA_MINUTES: int = 15
    QUOTE_VALID_MINUTES: int = 30
    PICKUP_WINDOW_HOURS: int = 48
    PICKUP_EXTENSION_HOURS: int = 24

    # ── File storage (local disk, signed URLs) ────────────────────────────────
    # PUBLIC_BASE_URL is what signed upload/download URLs point at — set it to your
    # machine's LAN IP (e.g. http://192.168.1.50:8000) when testing on a phone.
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    UPLOAD_DIR: str = "uploads"
    UPLOAD_MAX_BYTES: int = 10 * 1024 * 1024
    UPLOAD_URL_EXPIRE_SECONDS: int = 300
    DOWNLOAD_URL_EXPIRE_SECONDS: int = 3600

    # ── Prescription AI check ─────────────────────────────────────────────────
    AI_CLARITY_PASS_SCORE: int = 60

    # ── Payments ──────────────────────────────────────────────────────────────
    PAYMENT_GATEWAY: str = "mock"
    PAYMENT_WEBHOOK_SECRET: str = "dev-payment-webhook-secret"

    # ── Push notifications (Expo push service — free, no account needed) ─────
    EXPO_PUSH_ENABLED: bool = True

    # ── App ───────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    # Sri Lanka is a fixed UTC+05:30 (no DST); used for human-readable chat timestamps.
    APP_UTC_OFFSET_MINUTES: int = 330
    CORS_ORIGINS: list[str] = [
        "http://localhost:19006",
        "http://localhost:8081",
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


settings = Settings()
