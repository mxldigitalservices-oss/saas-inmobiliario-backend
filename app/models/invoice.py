from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, model_validator
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.base import Money, TenantDocument, period_of, utcnow
from app.models.enums import IncomeType, InvoiceStatus, PaymentMethod


class InvoiceLineRef(BaseModel):
    type: str  # "unit" | "property"
    id: PydanticObjectId


class InvoiceLine(BaseModel):
    description: str
    ref: Optional[InvoiceLineRef] = None
    qty: Money = Decimal("1")
    unit_price: Money = Decimal("0")
    itbis_rate: Money = Decimal("0.18")
    itbis: Money = Decimal("0")
    total: Money = Decimal("0")


class InvoiceTotals(BaseModel):
    subtotal: Money = Decimal("0")
    itbis: Money = Decimal("0")
    total: Money = Decimal("0")
    itbis_retained: Money = Decimal("0")
    isr_retained: Money = Decimal("0")
    currency: str = "DOP"


class InvoicePayment(BaseModel):
    method: PaymentMethod = PaymentMethod.CASH
    gateway_id: Optional[PydanticObjectId] = None
    paid_at: Optional[datetime] = None


class InvoiceVoid(BaseModel):
    at: datetime = Field(default_factory=utcnow)
    reason: Optional[str] = None
    by: Optional[PydanticObjectId] = None


class Invoice(TenantDocument):
    """Factura emitida. Fuente de datos del Reporte 607 (ventas) de la DGII."""

    number: str
    ncf: Optional[str] = None
    ncf_type: Optional[str] = None
    ncf_modified: Optional[str] = None  # para notas de crédito/débito
    client_id: Optional[PydanticObjectId] = None
    client_snapshot: Dict[str, Any] = Field(default_factory=dict)
    contract_id: Optional[PydanticObjectId] = None
    income_type: IncomeType = IncomeType.OPERACIONES
    lines: List[InvoiceLine] = Field(default_factory=list)
    totals: InvoiceTotals = Field(default_factory=InvoiceTotals)
    payment: InvoicePayment = Field(default_factory=InvoicePayment)
    status: InvoiceStatus = InvoiceStatus.ISSUED
    voided: Optional[InvoiceVoid] = None
    issued_at: datetime = Field(default_factory=utcnow)
    issued_by: Optional[PydanticObjectId] = None
    period: Optional[str] = None  # 'YYYY-MM' para agregaciones 607/608

    @model_validator(mode="after")
    def fill_period(self):
        if not self.period:
            self.period = period_of(self.issued_at)
        return self

    class Settings:
        name = "invoices"
        indexes = [
            IndexModel(
                [("tenant_id", ASCENDING), ("number", ASCENDING)],
                unique=True,
                name="uq_invoice_tenant_number",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("ncf", ASCENDING)],
                unique=True,
                name="uq_invoice_tenant_ncf",
                partialFilterExpression={"ncf": {"$type": "string"}},
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("issued_at", DESCENDING)],
                name="ix_invoice_tenant_issued",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("client_id", ASCENDING)],
                name="ix_invoice_tenant_client",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("status", ASCENDING), ("period", ASCENDING)],
                name="ix_invoice_tenant_status_period",
            ),
        ]
