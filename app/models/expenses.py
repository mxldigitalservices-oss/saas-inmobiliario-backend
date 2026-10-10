from datetime import datetime
from decimal import Decimal
from typing import Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator, model_validator
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.base import Money, TenantDocument, ensure_non_negative, period_of, utcnow
from app.models.enums import DGIIPaymentForm, ExpenseStatus, ExpenseType, TaxIdType


class Supplier(BaseModel):
    name: str
    tax_id_type: TaxIdType = TaxIdType.RNC
    tax_id: str  # RNC o cédula del proveedor (obligatorio para el 606)


class ExpenseAmounts(BaseModel):
    """Montos exigidos por el Reporte 606 de la DGII."""

    services_amount: Money = Decimal("0")  # monto facturado en servicios
    goods_amount: Money = Decimal("0")  # monto facturado en bienes
    total_amount: Money = Decimal("0")  # total facturado
    itbis_billed: Money = Decimal("0")  # ITBIS facturado
    itbis_withheld: Money = Decimal("0")  # ITBIS retenido
    itbis_proportionality: Money = Decimal("0")  # ITBIS sujeto a proporcionalidad
    itbis_to_cost: Money = Decimal("0")  # ITBIS llevado al costo
    itbis_to_advance: Money = Decimal("0")  # ITBIS por adelantar
    itbis_perceived: Money = Decimal("0")  # ITBIS percibido en compras
    isr_withholding_type: Optional[str] = None  # tipo de retención en ISR
    isr_withheld: Money = Decimal("0")  # monto retención renta
    isr_perceived: Money = Decimal("0")  # ISR percibido en compras
    selective_tax: Money = Decimal("0")  # impuesto selectivo al consumo
    other_taxes: Money = Decimal("0")  # otros impuestos/tasas
    legal_tip: Money = Decimal("0")  # monto propina legal
    currency: str = "DOP"

    @field_validator(
        "services_amount",
        "goods_amount",
        "total_amount",
        "itbis_billed",
        "itbis_withheld",
        "itbis_proportionality",
        "itbis_to_cost",
        "itbis_to_advance",
        "itbis_perceived",
        "isr_withheld",
        "isr_perceived",
        "selective_tax",
        "other_taxes",
        "legal_tip",
    )
    @classmethod
    def non_negative(cls, v):
        return ensure_non_negative(v)


class Expense(TenantDocument):
    """Gasto operativo de la agencia. Fuente del Reporte 606 (compras) DGII."""

    supplier: Supplier
    expense_type: ExpenseType = ExpenseType.TRABAJOS_SUMINISTROS_SERVICIOS
    description: Optional[str] = None
    category: Optional[str] = None  # categoría interna libre (oficina, publicidad...)
    ncf: Optional[str] = None
    ncf_modified: Optional[str] = None
    receipt_date: datetime = Field(default_factory=utcnow)  # fecha del comprobante
    payment_date: Optional[datetime] = None
    payment_form: DGIIPaymentForm = DGIIPaymentForm.EFECTIVO
    amounts: ExpenseAmounts = Field(default_factory=ExpenseAmounts)
    status: ExpenseStatus = ExpenseStatus.RECORDED
    attachment_media_id: Optional[PydanticObjectId] = None
    created_by: Optional[PydanticObjectId] = None
    period: Optional[str] = None  # 'YYYY-MM' para agregaciones 606

    @model_validator(mode="after")
    def fill_period(self):
        if not self.period:
            self.period = period_of(self.receipt_date)
        return self

    class Settings:
        name = "expenses"
        indexes = [
            IndexModel(
                [
                    ("tenant_id", ASCENDING),
                    ("supplier.tax_id", ASCENDING),
                    ("ncf", ASCENDING),
                ],
                unique=True,
                name="uq_expense_tenant_supplier_ncf",
                partialFilterExpression={"ncf": {"$type": "string"}},
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("receipt_date", DESCENDING)],
                name="ix_expense_tenant_receipt_date",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("status", ASCENDING), ("period", ASCENDING)],
                name="ix_expense_tenant_status_period",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("expense_type", ASCENDING)],
                name="ix_expense_tenant_type",
            ),
        ]
