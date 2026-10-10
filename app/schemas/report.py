from decimal import Decimal
from typing import List, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from app.models.base import Money
from app.schemas.common import PERIOD_REGEX


class ReportQuery(BaseModel):
    period: str = Field(pattern=PERIOD_REGEX)  # YYYY-MM


class Report607Row(BaseModel):
    """Una línea del Reporte 607 (ventas) de la DGII."""

    invoice_id: Optional[PydanticObjectId] = None
    rnc_cedula: Optional[str] = None
    tipo_identificacion: Optional[str] = None  # 1 = RNC, 2 = Cédula, 3 = Pasaporte
    ncf: Optional[str] = None
    ncf_modificado: Optional[str] = None
    tipo_ingreso: str = "01"
    fecha_comprobante: str  # AAAAMMDD
    fecha_retencion: Optional[str] = None
    monto_facturado: Money = Decimal("0")
    itbis_facturado: Money = Decimal("0")
    itbis_retenido: Money = Decimal("0")
    retencion_renta: Money = Decimal("0")
    forma_pago: Optional[str] = None


class Report606Row(BaseModel):
    """Una línea del Reporte 606 (compras y gastos) de la DGII."""

    expense_id: Optional[PydanticObjectId] = None
    rnc_cedula: str
    tipo_identificacion: Optional[str] = None
    tipo_bienes_servicios: str
    ncf: Optional[str] = None
    ncf_modificado: Optional[str] = None
    fecha_comprobante: str  # AAAAMMDD
    fecha_pago: Optional[str] = None
    monto_servicios: Money = Decimal("0")
    monto_bienes: Money = Decimal("0")
    total_facturado: Money = Decimal("0")
    itbis_facturado: Money = Decimal("0")
    itbis_retenido: Money = Decimal("0")
    itbis_proporcionalidad: Money = Decimal("0")
    itbis_costo: Money = Decimal("0")
    itbis_adelantar: Money = Decimal("0")
    itbis_percibido: Money = Decimal("0")
    tipo_retencion_isr: Optional[str] = None
    retencion_renta: Money = Decimal("0")
    isr_percibido: Money = Decimal("0")
    impuesto_selectivo: Money = Decimal("0")
    otros_impuestos: Money = Decimal("0")
    propina_legal: Money = Decimal("0")
    forma_pago: str = "01"


class ReportTotals(BaseModel):
    count: int = 0
    monto_total: Money = Decimal("0")
    itbis_total: Money = Decimal("0")
    retenciones_total: Money = Decimal("0")


class Report607Response(BaseModel):
    period: str
    tenant_rnc: Optional[str] = None
    rows: List[Report607Row] = Field(default_factory=list)
    totals: ReportTotals = Field(default_factory=ReportTotals)


class Report606Response(BaseModel):
    period: str
    tenant_rnc: Optional[str] = None
    rows: List[Report606Row] = Field(default_factory=list)
    totals: ReportTotals = Field(default_factory=ReportTotals)
