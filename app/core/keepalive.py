"""Auto-petición periódica a la propia API (anti-sleep opcional).

Solo es necesario si activaste Serverless / App Sleeping en Railway. Railway duerme
un servicio tras 10 min sin tráfico saliente, así que el intervalo debe ser < 10 min.
"""
import asyncio
import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("app")

_task: Optional["asyncio.Task[None]"] = None


def _target_url() -> str:
    if settings.KEEPALIVE_URL:
        return settings.KEEPALIVE_URL
    if settings.RAILWAY_PUBLIC_DOMAIN:
        return "https://{}/health".format(settings.RAILWAY_PUBLIC_DOMAIN)
    return ""


async def _loop(url: str, interval: int) -> None:
    await asyncio.sleep(30)  # deja que la app termine de arrancar
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        while True:
            try:
                resp = await client.get(url)
                logger.info("keep-alive %s -> %s", url, resp.status_code)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("keep-alive falló (%s): %s", url, exc)
            await asyncio.sleep(interval)


def start_keepalive() -> None:
    global _task
    if not settings.KEEPALIVE_ENABLED:
        return
    url = _target_url()
    if not url:
        logger.warning(
            "KEEPALIVE_ENABLED=true pero falta KEEPALIVE_URL o RAILWAY_PUBLIC_DOMAIN"
        )
        return
    interval = max(30, settings.KEEPALIVE_INTERVAL_SECONDS)
    if interval >= 600:
        logger.warning("Intervalo keep-alive >= 10 min: Railway podría dormir el servicio")
    _task = asyncio.create_task(_loop(url, interval), name="keepalive")
    logger.info("Keep-alive activo: %s cada %ss", url, interval)


async def stop_keepalive() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
