"""AsyncEngine + AsyncSessionLocal — fábrica de sessões SQLAlchemy async."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from viraxis.config import settings

# ------------------------------------------------------------------ #
# Engine async (asyncpg)                                             #
# ------------------------------------------------------------------ #
engine = create_async_engine(
    settings.database_url_async,
    echo=settings.debug,          # loga SQL quando DEBUG=true
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,           # reconecta se o Postgres reiniciar
)

# ------------------------------------------------------------------ #
# Session factory                                                    #
# ------------------------------------------------------------------ #
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,       # evita lazy-load após commit
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection para FastAPI / testes.

    Uso:
        @app.get("/")
        async def handler(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
