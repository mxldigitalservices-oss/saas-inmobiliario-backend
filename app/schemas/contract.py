from datetime import datetime
from typing import Any, Dict, List, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from app.models.contract import ContractTarget, ContractTerms, PartySnapshot
from app.models.enums import ContractStatus, ContractType
from app.schemas.common import TimestampedOut


class ContractCreate(BaseModel):
    type: ContractType = ContractType.SALE
    target: ContractTarget
    client_id: PydanticObjectId
    reservation_request_id: Optional[PydanticObjectId] = None
    agent_id: Optional[PydanticObjectId] = None
    terms: ContractTerms = Field(default_factory=ContractTerms)


class ContractUpdate(BaseModel):
    """Solo editable mientras el contrato esté en borrador."""

    agent_id: Optional[PydanticObjectId] = None
    terms: Optional[ContractTerms] = None


class ContractSignRequest(BaseModel):
    signed_at: Optional[datetime] = None


class ContractCancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class ContractOut(TimestampedOut):
    tenant_id: PydanticObjectId
    number: str
    type: ContractType
    status: ContractStatus
    target: ContractTarget
    client_id: PydanticObjectId
    reservation_request_id: Optional[PydanticObjectId] = None
    agent_id: Optional[PydanticObjectId] = None
    terms: ContractTerms
    party_snapshot: PartySnapshot
    invoice_ids: List[PydanticObjectId] = Field(default_factory=list)
    signed_at: Optional[datetime] = None


class ContractPrintData(BaseModel):
    """Data estructurada para que el frontend genere el PDF del contrato."""

    contract: ContractOut
    agency: Dict[str, Any] = Field(default_factory=dict)
    property: Dict[str, Any] = Field(default_factory=dict)
    unit: Optional[Dict[str, Any]] = None
    client: Dict[str, Any] = Field(default_factory=dict)
    agent: Dict[str, Any] = Field(default_factory=dict)
