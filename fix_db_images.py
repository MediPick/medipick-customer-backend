import asyncio
from app.database import AsyncSessionLocal
from sqlalchemy import text

async def fix():
    async with AsyncSessionLocal() as session:
        # Pharmacies
        await session.execute(text("UPDATE pharmacies SET image = 'P1' WHERE name ILIKE '%healthguard%'"))
        await session.execute(text("UPDATE pharmacies SET image = 'P2' WHERE name ILIKE '%union%'"))
        await session.execute(text("UPDATE pharmacies SET image = 'P3' WHERE name ILIKE '%lanka%'"))
        await session.execute(text("UPDATE pharmacies SET image = 'P1' WHERE image IS NULL"))
        
        await session.commit()
        
        res = await session.execute(text("SELECT name, image FROM pharmacies ORDER BY name"))
        for r in res.fetchall():
            print(r)

if __name__ == "__main__":
    asyncio.run(fix())
