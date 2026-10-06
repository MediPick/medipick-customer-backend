"""
MediPick — Pharmacy Pydantic Schemas
Request/response models for the Pharmacies domain (A3).
Field names match src/api/pharmaciesApi.ts on the client.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.models.pharmacy import Pharmacy


class PharmacyOut(BaseModel):
    """Matches the client's `Pharmacy` interface."""
    id: str
    name: str
    address: str
    nmraLicense: str | None
    pharmacistName: str | None
    pharmacistRegNo: str | None
    latitude: float | None
    longitude: float | None
    distance: str
    rating: float
    ratingCount: int
    estimatedResponseTime: str
    isOpen: bool
    hasOffer: bool
    offerTag: str | None
    image: str | None
    isFavorite: bool | None
    favoriteId: str | None

    @staticmethod
    def from_pharmacy(
        p: Pharmacy,
        distance: str,
        is_favorite: bool | None = None,
        favorite_id: str | None = None,
    ) -> "PharmacyOut":
        return PharmacyOut(
            id=str(p.id),
            name=p.name,
            address=p.address or "",
            nmraLicense=p.nmra_license,
            pharmacistName=p.pharmacist_name,
            pharmacistRegNo=p.pharmacist_reg_no,
            latitude=float(p.latitude) if p.latitude is not None else None,
            longitude=float(p.longitude) if p.longitude is not None else None,
            distance=distance,
            rating=round(p.rating_total / p.rating_count, 1) if p.rating_count else 0.0,
            ratingCount=p.rating_count,
            estimatedResponseTime=p.estimated_response_time,
            isOpen=p.is_open,
            hasOffer=p.has_offer,
            offerTag=p.offer_tag,
            image=p.image,
            isFavorite=is_favorite,
            favoriteId=favorite_id,
        )


class AddFavoriteResponse(BaseModel):
    favoriteId: str
    pharmacyId: str
