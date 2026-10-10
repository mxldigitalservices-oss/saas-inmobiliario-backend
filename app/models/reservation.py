from datetime import datetime
from typing import Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.base import Money, TenantDocument
from app.models.enums import ReservationSource, ReservationStatus


class ReservationTarget(BaseModel):
    property_id: PydanticObjectId
    unit_id: Optional[PydanticObjectId] = None


class ReservationContact(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    message: Optional[str] = None


class ReservationDeposit(BaseModel):
    amount: Money
    currency: str = "USD"
    payment_ref: Optional[str] = None


class ReservationRequest(TenantDocument):
    """Solicitud de reserva. NO bloquea la unidad hasta que el agente confirma."""

    target: ReservationTarget
    client_id: Optional[PydanticObjectId] = None
    contact: ReservationContact
    status: ReservationStatus = ReservationStatus.PENDING
    handled_by: Optional[PydanticObjectId] = None
    decision_note: Optional[str] = None
    decided_at: Optional[datetime] = None
    deposit: Optional[ReservationDeposit] = None
    source: ReservationSource = ReservationSource.WEB

    class Settings:
        name = "reservation_requests"
        indexes = [
            IndexModel(
                [("tenant_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)],
                name="ix_reservation_tenant_status",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("target.unit_id", ASCENDING), ("status", ASCENDING)],
                name="ix_reservation_unit_status",
            ),
        ]
