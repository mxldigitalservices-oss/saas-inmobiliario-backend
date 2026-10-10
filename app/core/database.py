import logging
from typing import Optional

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.models import ALL_DOCUMENT_MODELS

logger = logging.getLogger("app")

_client: Optional[AsyncIOMotorClient] = None


async def init_db() -> None:
    """Conecta a MongoDB e inicializa Beanie con todos los modelos."""
    global _client
    try:
        _client = AsyncIOMotorClient(
            settings.MONGODB_URL, serverSelectionTimeoutMS=10000
        )
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
        _client.close()
        _client = None
