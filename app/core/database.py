from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.core.config import settings
from app.models.all_models import ALL_DOCUMENT_MODELS

_client: AsyncIOMotorClient = None

async def init_db():
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGODB_URL)
    
    db_name = settings.MONGODB_DB
    
    await init_beanie(
        database=_client[db_name],
        document_models=ALL_DOCUMENT_MODELS
    )

async def close_db():
    global _client
    if _client is not None:
        _client.close()
        _client = None
