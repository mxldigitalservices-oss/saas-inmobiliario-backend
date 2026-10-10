import logging
from typing import Optional

from beanie import init_beanie
from pymongo import AsyncMongoClient

from app.core.config import settings
from app.models import ALL_DOCUMENT_MODELS

logger = logging.getLogger("app")

_client: Optional[AsyncMongoClient] = None


async def init_db() -> None:
    """Conecta a MongoDB e inicializa Beanie 2.x (usa el cliente async de PyMongo)."""
    global _client
    try:
        _client = AsyncMongoClient(settings.MONGODB_URL, serverSelectionTimeoutMS=10000)
        await _client.admin.command("ping")
        await init_beanie(
            database=_client[settings.MONGODB_DB],
            document_models=ALL_DOCUMENT_MODELS,
        )
        logger.info("MongoDB conectado (db=%s)", settings.MONGODB_DB)
    except Exception:
        logger.exception("No se pudo conectar/inicializar MongoDB")
        raise


async def close_db() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def ping_db() -> None:
    """Lanza excepción si MongoDB no responde (usado por el health check)."""
    if _client is None:
        raise RuntimeError("Cliente MongoDB no inicializado")
    await _client.admin.command("ping")
