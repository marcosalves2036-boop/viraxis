import asyncio
from viraxis.infrastructure.database.session import engine
from sqlalchemy import text

async def test():
    async with engine.connect() as conn:
        r = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
        tables = [row[0] for row in r]
        print("Tabelas:", tables)

asyncio.run(test())
