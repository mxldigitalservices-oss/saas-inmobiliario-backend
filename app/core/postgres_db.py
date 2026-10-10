"""Conexión a PostgreSQL con SQLAlchemy asíncrono (convive con MongoDB/Beanie)."""
import logging
from typing import AsyncIterator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger("app")


class Base(DeclarativeBase):
    """Base declarativa para todos los modelos relacionales."""


engine: Optional[AsyncEngine] = None
SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None


def postgres_enabled() -> bool:
    return bool(settings.DATABASE_URL)


async def init_postgres() -> None:
    """Crea el engine, verifica la conexión y (opcional) crea las tablas."""
    global engine, SessionLocal
    if not postgres_enabled():
        logger.warning("DATABASE_URL no definida: PostgreSQL desactivado")
        return

    # Importar los modelos registra las tablas en Base.metadata
    import app.models_sql  # noqa: F401

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.PG_ECHO,
        pool_size=settings.PG_POOL_SIZE,
        max_overflow=settings.PG_MAX_OVERFLOW,
        pool_pre_ping=True,  # evita conexiones muertas tras reinicios en Railway
        pool_recycle=1800,
    )
    SessionLocal = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            if settings.PG_AUTO_CREATE_TABLES:
                await conn.run_sync(Base.metadata.create_all)
        logger.info("PostgreSQL conectado")
    except Exception:
        logger.exception("No se pudo conectar/inicializar PostgreSQL")
        raise


async def close_postgres() -> None:
    global engine, SessionLocal
    if engine is not None:
        await engine.dispose()
    engine = None
    SessionLocal = None


async def get_db() -> AsyncIterator[AsyncSession]:
    """Dependencia FastAPI: una sesión por request.

    Hace commit si la ruta termina bien y rollback si lanza una excepción.
    """
    if SessionLocal is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="PostgreSQL no está configurado")
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
