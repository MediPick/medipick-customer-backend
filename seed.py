"""
MediPick — Dev seed data.

    cd backend
    .\\venv\\Scripts\\python.exe seed.py

Idempotent: re-running only adds what's missing (matched by name /
registration number), so it's safe to run against a DB you're already using.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

logging.disable(logging.WARNING)  # keep SQL echo out of the seed output

from app.core.timeutil import utcnow  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    HealthTip,
    InventoryItem,
    Medicine,
    MedicineCategory,
    Pharmacy,
    PharmacyStatus,
)
from app.services.health_tip_service import _preview, _read_time  # noqa: E402

CATEGORIES = [
    "Cold & Flu", "First Aid", "Vitamins", "Personal Care",
    "Chronic", "Skincare", "Supplements", "Baby Care",
]

# name, generic, brand, strength, form, manufacturer, category, rx, mrp, popularity, description, image
MEDICINES = [
    ("Panadol", "Paracetamol", "Panadol", "500mg", "Tablet", "GSK", "Cold & Flu", False, 45.0, 98,
     "Relief from headache, fever and mild to moderate pain.", "M1"),
    ("Piriton", "Chlorphenamine", "Piriton", "4mg", "Tablet", "GSK", "Cold & Flu", False, 38.0, 80,
     "Antihistamine for allergies, hay fever and itching.", "M2"),
    ("Cetirizine", "Cetirizine Hydrochloride", "Zyrtec", "10mg", "Tablet", "UCB", "Cold & Flu", False, 60.0, 72,
     "Non-drowsy relief from allergy symptoms.", "M3"),
    ("Jeevanee ORS", "Oral Rehydration Salts", "Jeevanee", "27.9g", "Sachet", "SPC", "First Aid", False, 30.0, 85,
     "Restores fluids and electrolytes lost through diarrhoea or heat.", "M4"),
    ("Dettol Antiseptic", "Chloroxylenol", "Dettol", "4.8%", "Liquid 125ml", "Reckitt", "First Aid", False, 420.0, 70,
     "Antiseptic liquid for cuts, grazes and personal hygiene.", "M5"),
    ("Siddhalepa Balm", "Herbal Balm", "Siddhalepa", "25g", "Balm", "Siddhalepa", "Personal Care", False, 350.0, 88,
     "Ayurvedic balm for headaches, colds and muscle aches.", None),
    ("Vitamin C", "Ascorbic Acid", "Redoxon", "1000mg", "Effervescent Tablet", "Bayer", "Vitamins", False, 1250.0, 76,
     "Supports the immune system.", None),
    ("Zinc Supplement", "Zinc Sulphate", "Zincovit", "20mg", "Tablet", "Apex", "Supplements", False, 480.0, 55,
     "Daily zinc supplement for immunity and recovery.", None),
    ("Cetaphil Moisturiser", "Moisturising Lotion", "Cetaphil", "250ml", "Lotion", "Galderma", "Skincare", False, 2950.0, 60,
     "Gentle moisturiser for dry and sensitive skin.", None),
    ("Omeprazole", "Omeprazole", "Losec", "20mg", "Capsule", "AstraZeneca", "Chronic", True, 95.0, 65,
     "Reduces stomach acid. Prescription required.", None),
    ("Metformin", "Metformin Hydrochloride", "Glucophage", "500mg", "Tablet", "Merck", "Chronic", True, 28.0, 68,
     "First-line treatment for type 2 diabetes. Prescription required.", None),
    ("Amoxicillin", "Amoxicillin", "Amoxil", "500mg", "Capsule", "GSK", "Chronic", True, 55.0, 58,
     "Antibiotic for bacterial infections. Prescription required.", None),
]

PHARMACIES = [
    ("Union Chemists", "PV-00123", "NMRA-2024-0451", "Dr. Nimali Perera", "SLMC-PH-2231", "+94112345678",
     "No. 45, Ward Place, Colombo 07", 6.9147, 79.8656, "5 - 15 mins", "10% off vitamins", 46, 10, "P2"),
    ("Healthguard Pharmacy", "PV-00456", "NMRA-2023-1187", "Mr. Kasun Silva", "SLMC-PH-1874", "+94112876543",
     "No. 212, High Level Road, Nugegoda", 6.8649, 79.8997, "10 - 20 mins", None, 43, 10, "P1"),
    ("City Pharmacy Dehiwala", "PV-00789", "NMRA-2022-0932", "Ms. Tharushi Fernando", "SLMC-PH-2410", "+94112723456",
     "No. 88, Galle Road, Dehiwala", 6.8511, 79.8653, "15 - 25 mins", "Free delivery over LKR 3000", 39, 10, "P3"),
]

# Per pharmacy: price multiplier vs MRP and which medicines are out of stock
PHARMACY_STOCK = {
    "Union Chemists": (0.95, set()),
    "Healthguard Pharmacy": (0.92, {"Cetaphil Moisturiser"}),
    "City Pharmacy Dehiwala": (0.97, {"Amoxicillin", "Zinc Supplement"}),
}

HEALTH_TIPS = [
    ("Staying Hydrated in the Heat", "Wellness",
     "Sri Lanka's heat and humidity make dehydration easy to miss. Aim for eight glasses of water a day, and more "
     "if you're outdoors or exercising. Signs of dehydration include dark urine, headaches and tiredness. Oral "
     "rehydration salts can help you recover quickly after bouts of diarrhoea or heavy sweating. King coconut "
     "water is a natural source of electrolytes too."),
    ("Taking Antibiotics the Right Way", "Medication",
     "Always finish the full course of antibiotics your doctor prescribes, even when you start feeling better. "
     "Stopping early lets the strongest bacteria survive and can make future infections harder to treat. Never "
     "share antibiotics or use leftovers from a previous illness, and ask your pharmacist whether to take them "
     "with food."),
    ("Managing Blood Sugar Every Day", "Chronic Care",
     "If you live with diabetes, small daily habits add up. Take your medicine at the same time each day, check "
     "your blood sugar as advised, and choose red rice and vegetables over refined carbohydrates. A 30-minute walk "
     "after dinner helps your body use insulin better. Keep regular appointments so your doctor can adjust your "
     "treatment."),
    ("Dengue: Protect Your Home", "Prevention",
     "Dengue mosquitoes breed in clean, still water. Empty flower pots, old tyres and gutters every week, cover "
     "water storage containers, and use repellent during the day when these mosquitoes bite. See a doctor if you "
     "have a high fever with body aches — and avoid ibuprofen or aspirin until dengue is ruled out."),
    ("Asthma Care During Monsoons", "Chronic Care",
     "The damp monsoon weather can trigger asthma attacks due to increased mold and cold air. Always carry your "
     "rescue inhaler when traveling. Use a preventer inhaler daily as prescribed, and try to stay indoors during "
     "heavy downpours or sudden temperature drops."),
    ("Healthy Heart Basics", "Wellness",
     "Cardiovascular diseases are a leading concern. Cut down on salt, deep-fried snacks, and sugar. Replace regular "
     "oil with healthier alternatives where possible, and try to get at least 150 minutes of moderate exercise like "
     "brisk walking every week. Regular blood pressure checks are essential after age 35."),
    ("Importance of Vitamin D", "Vitamins",
     "Despite the tropical sun, many office workers suffer from Vitamin D deficiency. Spend 15-20 minutes in early "
     "morning sunlight a few days a week. If you feel chronic fatigue or bone pain, ask your doctor for a blood test. "
     "They may recommend a simple Vitamin D supplement to boost your immunity and bone health."),
]


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        counts = {"categories": 0, "medicines": 0, "pharmacies": 0, "inventory": 0, "tips": 0}

        categories: dict[str, MedicineCategory] = {
            c.name: c for c in (await db.execute(select(MedicineCategory))).scalars().all()
        }
        for order, name in enumerate(CATEGORIES):
            if name not in categories:
                categories[name] = MedicineCategory(name=name, display_order=order)
                db.add(categories[name])
                counts["categories"] += 1
        await db.flush()

        medicines: dict[str, Medicine] = {m.name: m for m in (await db.execute(select(Medicine))).scalars().all()}
        for name, generic, brand, strength, form, mfr, cat, rx, mrp, pop, desc, image in MEDICINES:
            if name not in medicines:
                medicines[name] = Medicine(
                    name=name, generic_name=generic, brand_name=brand, strength=strength, dosage_form=form,
                    manufacturer=mfr, category_id=categories[cat].id, requires_prescription=rx,
                    mrp_price=mrp, popularity=pop, description=desc, image=image
                )
                db.add(medicines[name])
                counts["medicines"] += 1
            else:
                medicines[name].image = image
        await db.flush()

        pharmacies: dict[str, Pharmacy] = {
            p.registration_number: p for p in (await db.execute(select(Pharmacy))).scalars().all()
        }
        for (name, reg, nmra, pharmacist, pharm_reg, phone, address, lat, lng,
             eta, offer, rating_total, rating_count, image) in PHARMACIES:
            if reg not in pharmacies:
                pharmacies[reg] = Pharmacy(
                    name=name, registration_number=reg, nmra_license=nmra, pharmacist_name=pharmacist,
                    pharmacist_reg_no=pharm_reg, phone_number=phone, address=address, latitude=lat, longitude=lng,
                    estimated_response_time=eta, has_offer=offer is not None, offer_tag=offer,
                    rating_total=rating_total, rating_count=rating_count, is_open=True,
                    status=PharmacyStatus.APPROVED, image=image
                )
                db.add(pharmacies[reg])
                counts["pharmacies"] += 1
            else:
                pharmacies[reg].image = image
        await db.flush()

        existing_inventory = {
            (i.pharmacy_id, i.medicine_id) for i in (await db.execute(select(InventoryItem))).scalars().all()
        }
        for pharmacy in pharmacies.values():
            multiplier, out_of_stock = PHARMACY_STOCK.get(pharmacy.name, (0.95, set()))
            for medicine in medicines.values():
                if (pharmacy.id, medicine.id) in existing_inventory:
                    continue
                db.add(InventoryItem(
                    pharmacy_id=pharmacy.id,
                    medicine_id=medicine.id,
                    unit_price=round(float(medicine.mrp_price) * multiplier, 2),
                    stock_quantity=0 if medicine.name in out_of_stock else 120,
                ))
                counts["inventory"] += 1
        await db.flush()

        existing_tips = {t.title for t in (await db.execute(select(HealthTip))).scalars().all()}
        for title, category, body in HEALTH_TIPS:
            if title not in existing_tips:
                db.add(HealthTip(
                    title=title, category=category, content_body=body, preview_text=_preview(body),
                    read_time_mins=_read_time(body), is_published=True, published_at=utcnow(),
                ))
                counts["tips"] += 1

        await db.commit()
        print("Seed complete - added:", ", ".join(f"{v} {k}" for k, v in counts.items()))


if __name__ == "__main__":
    asyncio.run(seed())
