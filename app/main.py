"""
MediPick — FastAPI Application Factory
"""
from __future__ import annotations

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.realtime import sio


def create_application() -> FastAPI:
    app = FastAPI(
        title="MediPick API",
        description="MediPick Customer-Facing REST API — Sri Lanka Pharmacy Marketplace",
        version="3.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception Handlers ────────────────────────────────────────────────────
    register_exception_handlers(app)

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    from app.core.rate_limit import setup_rate_limiting
    setup_rate_limiting(app)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(api_router)

    # ── Health Check ──────────────────────────────────────────────────────────
    @app.get("/", tags=["Health"])
    async def root() -> dict:
        return {
            "success": True,
            "data": {
                "message": "MediPick API is running",
                "version": "3.0.0",
                "environment": settings.APP_ENV,
                "docs": "/docs",
            },
        }

    return app


fastapi_app = create_application()

# Socket.IO (live order chat, A13.1) is served at /socket.io/; every other path
# falls through to FastAPI. Keep the name `app` — it's uvicorn's target.
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path="socket.io")
