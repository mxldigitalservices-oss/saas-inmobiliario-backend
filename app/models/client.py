from typing import Optional

from beanie import PydanticObjectId
from pydantic import BaseModel
from pymongo import ASCENDING, IndexModel

from app.models.base import TenantDocument
from app.models.enums import ClientStage, ClientType, TaxIdType


class TaxId(BaseModel):
    type: TaxIdType = TaxIdType.CEDULA
    number: str


class Client(TenantDocument):
    """Comprador, inquilino o lead de la agencia."""

    type: ClientType = ClientType.PERSON
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    tax_id: Optional[TaxId] = None  # necesario para el Reporte 607
    address: Optional[str] = None
    stage: ClientStage = ClientStage.LEAD
    assigned_agent_id: Optional[PydanticObjectId] = None
    notes: Optional[str] = None

    class Settings:
        name = "clients"
        indexes = [
            IndexModel(
                [("tenant_id", ASCENDING), ("tax_id.number", ASCENDING)],
                name="ix_client_tenant_taxid",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("email", ASCENDING)],
                name="ix_client_tenant_email",
            ),
            IndexModel(
                [
                    ("tenant_id", ASCENDING),
                    ("assigned_agent_id", ASCENDING),
                    ("stage", ASCENDING),
                ],
                name="ix_client_tenant_agent_stage",
            ),
        ]
