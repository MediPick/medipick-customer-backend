"""
MediPick — Models Package
Import all models here so Alembic auto-detects them for migrations.
Order matters for FK resolution: User must come before Customer and RefreshToken.
"""
from app.models.user import User, UserRole
from app.models.customer import Customer
from app.models.refresh_token import RefreshToken
from app.models.pharmacy import Pharmacy, PharmacyStatus
from app.models.medicine_category import MedicineCategory
from app.models.medicine import Medicine
from app.models.inventory_item import InventoryItem
from app.models.favorite_pharmacy import FavoritePharmacy
from app.models.prescription import Prescription, PrescriptionStatus
from app.models.order import Order, OrderItem, OrderRating, OrderState, OrderType, PaymentMethod
from app.models.quote import Quote, QuoteItem, QuoteStatus
from app.models.payment import PaymentStatus, PaymentTransaction
from app.models.chat import ChatMessage, ChatSession, SenderRole
from app.models.notification import Notification, NotificationType
from app.models.health_tip import HealthTip
from app.models.issue import Issue, IssueStatus, IssueType

__all__ = [
    "User", "UserRole", "Customer", "RefreshToken",
    "Pharmacy", "PharmacyStatus", "MedicineCategory", "Medicine", "InventoryItem",
    "FavoritePharmacy",
    "Prescription", "PrescriptionStatus",
    "Order", "OrderItem", "OrderRating", "OrderState", "OrderType", "PaymentMethod",
    "Quote", "QuoteItem", "QuoteStatus",
    "PaymentTransaction", "PaymentStatus",
    "ChatSession", "ChatMessage", "SenderRole",
    "Notification", "NotificationType",
    "HealthTip",
    "Issue", "IssueStatus", "IssueType",
]
