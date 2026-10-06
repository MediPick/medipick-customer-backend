"""MediPick — API v1 Router"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    health_tips,
    issues,
    medicines,
    messages,
    notifications,
    orders,
    payments,
    pharmacies,
    prescriptions,
    quotes,
    uploads,
    users,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(pharmacies.router)
api_router.include_router(medicines.router)
api_router.include_router(prescriptions.router)
api_router.include_router(uploads.router)
api_router.include_router(orders.router)
api_router.include_router(quotes.router)
api_router.include_router(messages.router)
api_router.include_router(payments.router)
api_router.include_router(notifications.router)
api_router.include_router(health_tips.router)
api_router.include_router(issues.router)
