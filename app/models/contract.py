from datetime import datetime
from typing import Any, Dict, List, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel

from app.models.base import Money, TenantDocument
from app.models.enums import ContractStatus, ContractType


class ContractTarget(BaseModel):
    property_id: PydanticObjectId
    unit_id: Optional[PydanticObjectId] = None


class PaymentInstallment(BaseModel):
    due: datetime
    amount: Money
    paid: bool = False


class ContractTerms(BaseModel):
    price: Optional[Money] = None
    currency: str = "USD"
    down_payment: Optional[Money] = None
    payment_schedule: List[PaymentInstallment] = Field(default_factory=list)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    clauses: List[str] = Field(default_factory=list)


class PartySnapshot(BaseModel):
    """Datos congelados de las partes, listos para que el frontend genere el PDF."""

    seller: Dict[str, Any] = Field(default_factory=dict)
    buyer: Dict[str, Any] = Field(default_factory=dict)


class Contract(TenantDocument):
    """Contrato de venta, alquiler o reserva."""

    number: str
    type: ContractType = ContractType.SALE
    status: ContractStatus = ContractStatus.DRAFT
    target: ContractTarget
    client_id: PydanticObjectId
    reservation_request_id: Optional[PydanticObjectId] = None
    agent_id: Optional[PydanticObjectId] = None
    terms: ContractTerms = Field(default_factory=ContractTerms)
    party_snapshot: PartySnapshot = Field(default_factory=PartySnapshot)
    invoice_ids: List[PydanticObjectId] = Field(default_factory=list)
    signed_at: Optional[datetime] = None

    class Settings:
        name = "contracts"
        indexes = [
            IndexModel(
                [("tenant_id", ASCENDING), ("number", ASCENDING)],
                unique=True,
                name="uq_contract_tenant_number",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("client_id", ASCENDING)],
                name="ix_contract_tenant_client",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("status", ASCENDING)],
                name="ix_contract_tenant_status",
            ),
        ]
