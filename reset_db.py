import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def run():
    engine = create_async_engine('postgresql+asyncpg://postgres:sameera@localhost:5432/medipick_db', isolation_level='AUTOCOMMIT')
    async with engine.connect() as conn:
        try:
            await conn.execute(text('DROP SCHEMA public CASCADE; CREATE SCHEMA public;'))
        except Exception as e:
            print("Schema drop failed:", e)
            
        try:
            await conn.execute(text('DROP TYPE IF EXISTS user_role_enum CASCADE;'))
        except Exception as e:
            print("Type drop failed:", e)
            
        print("Schema reset successful.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run())
