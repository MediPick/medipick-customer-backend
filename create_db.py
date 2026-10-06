import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def create_db():
    engine = create_async_engine("postgresql+asyncpg://postgres:sameera@localhost:5432/postgres", isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'medipick_db'"))
        if not result.scalar():
            await conn.execute(text("CREATE DATABASE medipick_db"))
            print("Database 'medipick_db' created successfully.")
        else:
            print("Database 'medipick_db' already exists.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_db())
