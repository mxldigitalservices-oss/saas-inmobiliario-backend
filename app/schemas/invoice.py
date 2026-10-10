from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.base import Money, ensure_non_negative
from app.models.enums import IncomeType, InvoiceStatus, PaymentMethod
from app.models.invoice import (
    InvoiceLine,
    InvoiceLineRef,
    InvoicePayment,
    InvoiceTotals,
    InvoiceVoid,
)
from app.schemas.common import PERIOD_REGEX, TimestampedOut
from app.schemas.ncf import NCF_TYPE_PATTERN


class InvoiceLineIn(BaseModel):
    """Totales de línea e ITBIS los calcula el servidor."""

    description: str = Field(min_length=1, max_length=300)
    ref: Optional[InvoiceLineRef] = None
    qty: Money = Decimal("1")
    unit_price: Money = Decimal("0")
    itbis_rate: Money = Decimal("0.18")

    @field_validator("qty")
    @classmethod
    def _qty(cls, v):
        if v <= 0:
            raise ValueError("La cantidad debe ser mayor que cero")
        return v

    @field_validator("unit_price")
    @classmethod
    def _price(cls, v):
        return ensure_non_negative(v)

    @field_validator("itbis_rate")
    @classmethod
    def _rate(cls, v):
        if v < 0 or v > 1:
            raise ValueError("itbis_rate debe estar entre 0 y 1 (ej. 0.18)")
        return v


class InvoiceCreate(BaseModel):
    client_id: Optional[PydanticObjectId] = None
    client_snapshot: Optional[Dict[str, Any]] = None
    contract_id: Optional[PydanticObjectId] = None
    ncf_type: Optional[str] = Field(None, pattern=NCF_TYPE_PATTERN)
    ncf_modified: Optional[str] = Field(None, max_length=13)
    income_type: IncomeType = IncomeType.OPERACIONES
    lines: List[InvoiceLineIn] = Field(min_length=1, max_length=100)
    payment: InvoicePayment = Field(default_factory=InvoicePayment)
    currency: str = Field("DOP", min_length=3, max_length=3)
    issued_at: Optional[datetime] = None
    itbis_retained: Money = Decimal("0")
    isr_retained: Money = Decimal("0")
    notes: Optional[str] = Field(None, max_length=1000)

    # mode="before": normaliza (strip + mayúsculas) ANTES de validar el pattern
    @field_validator("ncf_type", "ncf_modified", "currency", mode="before")
    @classmethod
    def _upper(cls, v):
        if isinstance(v, str):
            v = v.strip().upper()
            return v or None
        return v

    @field_validator("itbis_retained", "isr_retained")
    @classmethod
    def _non_negative(cls, v):
        return ensure_non_negative(v)


class InvoicePaymentUpdate(BaseModel):
    method: PaymentMethod
    gateway_id: Optional[PydanticObjectId] = None
    paid_at: Optional[datetime] = None


class InvoiceVoidRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class InvoiceOut(TimestampedOut):
    tenant_id: PydanticObjectId
    number: str
    ncf: Optional[str] = None
    ncf_type: Optional[str] = None
    ncf_modified: Optional[str] = None
    client_id: Optional[PydanticObjectId] = None
    client_snapshot: Dict[str, Any] = Field(default_factory=dict)
    contract_id: Optional[PydanticObjectId] = None
    income_type: IncomeType
    lines: List[InvoiceLine] = Field(default_factory=list)
    totals: InvoiceTotals
    payment: InvoicePayment
    status: InvoiceStatus
    voided: Optional[InvoiceVoid] = None
    issued_at: datetime
    issued_by: Optional[PydanticObjectId] = None
    period: Optional[str] = None


class InvoiceFilter(BaseModel):
    status: Optional[InvoiceStatus] = None
    client_id: Optional[PydanticObjectId] = None
    period: Optional[str] = Field(None, pattern=PERIOD_REGEX)
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    ncf: Optional[str] = Field(None, max_length=13)

    @model_validator(mode="after")
    def _range(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from no puede ser posterior a date_to")
        return self
