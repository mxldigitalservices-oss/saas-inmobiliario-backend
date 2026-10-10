"""Diagnóstico de salud: MongoDB, Redis, PostgreSQL y estado de la aplicación."""
import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

from sqlalchemy import text

from app.core import database, postgres_db, redis_client
from app.core.config import settings

STARTED_AT = time.time()
CHECK_TIMEOUT = 3.0  # segundos por componente

# Componentes críticos: si fallan, el estado global es "unhealthy" (HTTP 503).
# Los no críticos (Redis = caché) solo dejan el estado en "degraded" (HTTP 200).
CRITICAL = {"mongodb", "postgres"}


async def _timed(name: str, fn: Callable[[], Awaitable[None]]) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        await asyncio.wait_for(fn(), timeout=CHECK_TIMEOUT)
        status, error = "healthy", None
    except asyncio.TimeoutError:
        status, error = "unhealthy", "timeout ({}s)".format(CHECK_TIMEOUT)
    except Exception as exc:
        status, error = "unhealthy", "{}: {}".format(type(exc).__name__, str(exc)[:200])
    result: Dict[str, Any] = {
        "status": status,
        "latency_ms": round((time.perf_counter() - start) * 1000, 1),
        "critical": name in CRITICAL,
    }
    if error:
        result["error"] = error
    return result


async def _check_mongo() -> None:
    await database.ping_db()


async def _check_redis() -> None:
    if redis_client.redis_client is None:
        raise RuntimeError("Cliente Redis no inicializado")
    await redis_client.redis_client.ping()


async def _check_postgres() -> None:
    if postgres_db.SessionLocal is None:
        raise RuntimeError("Sesión PostgreSQL no inicializada")
    async with postgres_db.SessionLocal() as session:
        await session.execute(text("SELECT 1"))


def _read_int(path: str) -> Optional[int]:
    try:
        raw = open(path).read().strip()
        return None if raw == "max" else int(raw)
    except Exception:
        return None


def memory_info() -> Dict[str, Any]:
    """Memoria del proceso (RSS) y, si existe, la del contenedor (cgroup)."""
    info: Dict[str, Any] = {}
    try:
        for line in open("/proc/self/status"):
            if line.startswith("VmRSS:"):
                info["process_rss_mb"] = round(int(line.split()[1]) / 1024, 1)
                break
    except Exception:
        try:
            import resource

            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # Linux: KB, macOS: bytes
            info["process_rss_mb"] = round(
                rss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1
            )
        except Exception:
            pass
    used = _read_int("/sys/fs/cgroup/memory.current")
    limit = _read_int("/sys/fs/cgroup/memory.max")
    if used is not None:
        info["container_used_mb"] = round(used / 1024 / 1024, 1)
    if limit is not None:
        info["container_limit_mb"] = round(limit / 1024 / 1024, 1)
    return info


async def build_status() -> Dict[str, Any]:
    names = ["mongodb", "redis"]
    coros = [_timed("mongodb", _check_mongo), _timed("redis", _check_redis)]
    if postgres_db.postgres_enabled():
        names.append("postgres")
        coros.append(_timed("postgres", _check_postgres))
    results = await asyncio.gather(*coros)
    components: Dict[str, Any] = dict(zip(names, results))
    if not postgres_db.postgres_enabled():
        components["postgres"] = {"status": "disabled", "critical": False}

    failed = [n for n, c in components.items() if c["status"] == "unhealthy"]
    if any(n in CRITICAL for n in failed):
        overall = "unhealthy"
    elif failed:
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "failed_components": failed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "app": {
            "name": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
            "python": sys.version.split()[0],
            "uptime_seconds": int(time.time() - STARTED_AT),
            "pid": os.getpid(),
            "memory": memory_info(),
            "keepalive_enabled": settings.KEEPALIVE_ENABLED,
        },
        "components": components,
    }
