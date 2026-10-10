import os
from typing import Optional

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.models import ALL_DOCUMENT_MODELS

_client: Optional[AsyncIOMotorClient] = None


async def init_db(
    mongo_url: Optional[str] = None, db_name: Optional[str] = None
) -> AsyncIOMotorClient:
    """Conecta a MongoDB e inicializa Beanie (crea colecciones e índices)."""
    global _client
    mongo_url = (
        mongo_url
        or os.getenv("MONGODB_URL")
        or os.getenv("MONGO_URL")
        or "mongodb://localhost:27017"
    )
    db_name = db_name or os.getenv("MONGODB_DB") or "inmobiliaria_saas"

    _client = AsyncIOMotorClient(mongo_url, tz_aware=True)
    await init_beanie(database=_client[db_name], document_models=ALL_DOCUMENT_MODELS)
    return _client


async def close_db() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
