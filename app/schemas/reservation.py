from datetime import date, datetime
from typing import Literal, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import ReservationSource, ReservationStatus
from app.models.reservation import (
    ReservationContact,
    ReservationDeposit,
    ReservationTarget,
)
from app.schemas.common import TimestampedOut, normalize_email


class ReservationPublicCreate(BaseModel):
    """Solicitud enviada desde el sitio público. NO bloquea la unidad."""

    property_id: PydanticObjectId
    unit_id: Optional[PydanticObjectId] = None
    name: str = Field(min_length=2, max_length=120)
    email: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=30)
    message: Optional[str] = Field(None, max_length=1000)

    @field_validator("email")
    @classmethod
    def _email(cls, v: Optional[str]) -> Optional[str]:
        return normalize_email(v) if v else None

    @model_validator(mode="after")
    def _contact_required(self):
        if not self.email and not self.phone:
            raise ValueError("Debe indicar un email o un teléfono de contacto")
        return self


class ReservationManualCreate(ReservationPublicCreate):
    """Solicitud registrada manualmente por el agente (llamada, WhatsApp...)."""

    client_id: Optional[PydanticObjectId] = None
    source: ReservationSource = ReservationSource.MANUAL
    deposit: Optional[ReservationDeposit] = None


class ReservationDecision(BaseModel):
    """Confirmación o rechazo manual por parte del agente."""

    action: Literal["confirm", "reject"]
    note: Optional[str] = Field(None, max_length=500)
    deposit: Optional[ReservationDeposit] = None


class ReservationOut(TimestampedOut):
    tenant_id: PydanticObjectId
    target: ReservationTarget
    client_id: Optional[PydanticObjectId] = None
    contact: ReservationContact
    status: ReservationStatus
    handled_by: Optional[PydanticObjectId] = None
    decision_note: Optional[str] = None
    decided_at: Optional[datetime] = None
    deposit: Optional[ReservationDeposit] = None
    source: ReservationSource


class ReservationFilter(BaseModel):
    status: Optional[ReservationStatus] = None
    property_id: Optional[PydanticObjectId] = None
    unit_id: Optional[PydanticObjectId] = None
    source: Optional[ReservationSource] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None

    @model_validator(mode="after")
    def _range(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from no puede ser posterior a date_to")
        return self
