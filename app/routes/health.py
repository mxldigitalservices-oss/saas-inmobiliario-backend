import secrets
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.health import build_status

router = APIRouter(tags=["health"])


@router.get("/status")
@router.get("/api/v1/health")
async def status(x_health_token: Optional[str] = Header(default=None)):
    """Diagnóstico completo. Responde 503 solo si falla un componente crítico."""
    if settings.HEALTH_TOKEN and not secrets.compare_digest(
        x_health_token or "", settings.HEALTH_TOKEN
    ):
        raise HTTPException(status_code=401, detail="Token de diagnóstico inválido")
    data = await build_status()
    return JSONResponse(
        content=data, status_code=503 if data["status"] == "unhealthy" else 200
    )
