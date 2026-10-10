import logging
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.core.config import settings
from app.models.all_models import ALL_DOCUMENT_MODELS

logger = logging.getLogger(__name__)
_client: AsyncIOMotorClient = None

async def init_db():
    global _client
    try:
        if _client is None:
            _client = AsyncIOMotorClient(settings.MONGODB_URL)
        
        db_name = settings.MONGODB_DB
        logger.info(f"Conectando a MongoDB base: {db_name}...")
        
        await init_beanie(
            database=_client[db_name],
            document_models=ALL_DOCUMENT_MODELS
        )
        logger.info("¡Beanie inicializado exitosamente!")
    except Exception as e:
        logger.error(f"ERROR CRITICO EN INIT_DB: {e}", exc_info=True)
        raise e

async def close_db():
    global _client
    if _client is not None:
        _client.close()
        _client = None
