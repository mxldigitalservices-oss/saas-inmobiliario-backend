"""Cliente Redis asíncrono (caché, sesiones, contadores rápidos).

Si Redis no está disponible, la app sigue funcionando: las funciones de caché
fallan en silencio (devuelven None/False) y registran el error en los logs.
"""
import json
import logging
from typing import Any, Optional

from fastapi import HTTPException
from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings

logger = logging.getLogger("app")

_pool: Optional[ConnectionPool] = None
redis_client: Optional[Redis] = None


async def init_redis() -> None:
    """Crea el pool, hace ping y registra en logs si Redis está activo."""
    global _pool, redis_client
    try:
        _pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )
        redis_client = Redis(connection_pool=_pool)
        await redis_client.ping()
        logger.info("Redis activo (ping OK)")
    except Exception:
        logger.exception("Redis no disponible; la caché quedará desactivada")
        await close_redis()


async def close_redis() -> None:
    global _pool, redis_client
    try:
        if redis_client is not None:
            await redis_client.aclose()
        if _pool is not None:
            await _pool.disconnect()
    except Exception:  # pragma: no cover
        logger.exception("Error cerrando Redis")
    finally:
        redis_client = None
        _pool = None


async def get_redis() -> Redis:
    """Dependencia FastAPI: devuelve el cliente o 503 si Redis no está disponible."""
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Redis no está disponible")
    return redis_client


# ---------------------------------------------------------------- caché básica
async def cache_get(key: str) -> Optional[str]:
    if redis_client is None:
        return None
    try:
        return await redis_client.get(key)
    except Exception:
        logger.exception("cache_get falló (%s)", key)
        return None


async def cache_set(key: str, value: str, ttl: Optional[int] = None) -> bool:
    if redis_client is None:
        return False
    try:
        await redis_client.set(key, value, ex=ttl or settings.REDIS_DEFAULT_TTL)
        return True
    except Exception:
        logger.exception("cache_set falló (%s)", key)
        return False


async def cache_delete(*keys: str) -> int:
    if redis_client is None or not keys:
        return 0
    try:
        return await redis_client.delete(*keys)
    except Exception:
        logger.exception("cache_delete falló (%s)", keys)
        return 0


# ------------------------------------------------------------------ helpers JSON
async def cache_get_json(key: str) -> Optional[Any]:
    raw = await cache_get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


async def cache_set_json(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    # default=str serializa fechas, Decimal y ObjectId
    return await cache_set(key, json.dumps(value, default=str), ttl)


async def cache_delete_pattern(pattern: str) -> int:
    """Borra todas las claves que coincidan (p. ej. 'tenant:<id>:properties:*').

    Usa SCAN (no bloquea Redis como KEYS).
    """
    if redis_client is None:
        return 0
    deleted = 0
    try:
        batch = []
        async for key in redis_client.scan_iter(match=pattern, count=200):
            batch.append(key)
            if len(batch) >= 200:
                deleted += await redis_client.delete(*batch)
                batch = []
        if batch:
            deleted += await redis_client.delete(*batch)
    except Exception:
        logger.exception("cache_delete_pattern falló (%s)", pattern)
    return deleted
