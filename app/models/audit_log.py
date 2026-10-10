from typing import Any, Dict, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.base import BaseDocument
from app.models.enums import AuditActorType


class AuditActor(BaseModel):
    type: AuditActorType = AuditActorType.USER
    id: Optional[PydanticObjectId] = None


class AuditEntity(BaseModel):
    type: str
    id: Optional[PydanticObjectId] = None


class AuditLog(BaseDocument):
    """Bitácora de acciones sensibles (canje de tokens, anulaciones, credenciales)."""

    tenant_id: Optional[PydanticObjectId] = None  # None = acción global del SaaS
    actor: AuditActor = Field(default_factory=AuditActor)
    action: str  # ej: "license.redeem", "invoice.void", "gateway.update"
    entity: Optional[AuditEntity] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
    ip: Optional[str] = None

    class Settings:
        name = "audit_logs"
        indexes = [
            IndexModel(
                [("tenant_id", ASCENDING), ("created_at", DESCENDING)],
                name="ix_audit_tenant_created",
            ),
            IndexModel([("action", ASCENDING)], name="ix_audit_action"),
        ]
