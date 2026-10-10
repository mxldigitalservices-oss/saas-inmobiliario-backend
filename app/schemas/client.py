import re
from typing import Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.client import TaxId
from app.models.enums import ClientStage, ClientType, TaxIdType
from app.schemas.common import TimestampedOut, normalize_email


class TaxIdIn(BaseModel):
    """RNC = 9 dígitos, cédula = 11 dígitos; pasaporte alfanumérico libre."""

    type: TaxIdType = TaxIdType.CEDULA
    number: str = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def _normalize(self):
        if self.type in (TaxIdType.RNC, TaxIdType.CEDULA):
            digits = re.sub(r"\D", "", self.number)
            expected = 9 if self.type == TaxIdType.RNC else 11
            if len(digits) != expected:
                raise ValueError(
                    f"El {self.type.value.upper()} debe tener {expected} dígitos"
                )
            self.number = digits
        else:
            self.number = self.number.strip().upper()
        return self


class ClientCreate(BaseModel):
    type: ClientType = ClientType.PERSON
    name: str = Field(min_length=2, max_length=160)
    email: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=30)
    tax_id: Optional[TaxIdIn] = None
    address: Optional[str] = Field(None, max_length=300)
    stage: ClientStage = ClientStage.LEAD
    assigned_agent_id: Optional[PydanticObjectId] = None
    notes: Optional[str] = Field(None, max_length=2000)

    @field_validator("email")
    @classmethod
    def _email(cls, v: Optional[str]) -> Optional[str]:
        return normalize_email(v) if v else None


class ClientUpdate(BaseModel):
    type: Optional[ClientType] = None
    name: Optional[str] = Field(None, min_length=2, max_length=160)
    email: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=30)
    tax_id: Optional[TaxIdIn] = None
    address: Optional[str] = Field(None, max_length=300)
    stage: Optional[ClientStage] = None
    assigned_agent_id: Optional[PydanticObjectId] = None
    notes: Optional[str] = Field(None, max_length=2000)

    @field_validator("email")
    @classmethod
    def _email(cls, v: Optional[str]) -> Optional[str]:
        return normalize_email(v) if v else None


class ClientOut(TimestampedOut):
    tenant_id: PydanticObjectId
    type: ClientType
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    tax_id: Optional[TaxId] = None
    address: Optional[str] = None
    stage: ClientStage
    assigned_agent_id: Optional[PydanticObjectId] = None
    notes: Optional[str] = None


class ClientFilter(BaseModel):
    q: Optional[str] = Field(None, max_length=120)
    stage: Optional[ClientStage] = None
    assigned_agent_id: Optional[PydanticObjectId] = None
    tax_id: Optional[str] = None
