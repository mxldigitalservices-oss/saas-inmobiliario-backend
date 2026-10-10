import logging
from typing import Any, Dict, Optional

from beanie import PydanticObjectId
from fastapi import Request

from app.models.audit_log import AuditActor, AuditEntity, AuditLog
from app.models.enums import AuditActorType

logger = logging.getLogger("audit")


async def write_audit(
    action: str,
    *,
    actor_type: AuditActorType = AuditActorType.USER,
    actor_id: Optional[PydanticObjectId] = None,
    tenant_id: Optional[PydanticObjectId] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[PydanticObjectId] = None,
    meta: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    """Registra una acción sensible. Un fallo de auditoría nunca rompe la petición."""
    try:
        ip = request.client.host if request is not None and request.client else None
        entry = AuditLog(
            tenant_id=tenant_id,
            actor=AuditActor(type=actor_type, id=actor_id),
            action=action,
            entity=AuditEntity(type=entity_type, id=entity_id) if entity_type else None,
            meta=meta or {},
            ip=ip,
        )
        await entry.insert()
    except Exception:  # pragma: no cover
        logger.exception("No se pudo escribir el registro de auditoría: %s", action)
