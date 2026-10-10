import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional, Tuple

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.audit import write_audit
from app.core.db_utils import date_range_filter, next_counter, raw_collection
from app.core.deps import (
    ADMIN_ROLES,
    STAFF_ROLES,
    STAFF_WRITE_ROLES,
    build_model,
    get_current_tenant,
    get_page_params,
    require_roles,
    require_writable_tenant,
)
from app.models.base import utcnow
from app.models.client import Client
from app.models.contract import Contract
from app.models.enums import InvoiceStatus, NCFStatus
from app.models.invoice import (
    Invoice,
    InvoiceLine,
    InvoicePayment,
    InvoiceTotals,
    InvoiceVoid,
)
from app.models.ncf_sequence import NCFSequence
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.common import PERIOD_REGEX, Page, PageParams
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceFilter,
    InvoiceOut,
    InvoicePaymentUpdate,
    InvoiceVoidRequest,
)
from app.schemas.report import Report607Response, Report607Row, ReportTotals

router = APIRouter(prefix="/invoices", tags=["invoices"])

InvoicePage = Page[InvoiceOut]
CENT = Decimal("0.01")
TIPO_ID = {"rnc": "1", "cedula": "2", "passport": "3"}


def _q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def invoice_filter(
    status_: Optional[InvoiceStatus] = Query(None, alias="status"),
    client_id: Optional[PydanticObjectId] = Query(None),
    period: Optional[str] = Query(None, pattern=PERIOD_REGEX),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    ncf: Optional[str] = Query(None, max_length=13),
) -> InvoiceFilter:
    return build_model(
        InvoiceFilter,
        status=status_,
        client_id=client_id,
        period=period,
        date_from=date_from,
        date_to=date_to,
        ncf=ncf,
    )


async def _get_invoice(tenant_id, invoice_id: PydanticObjectId) -> Invoice:
    invoice = await Invoice.find_one({"_id": invoice_id, "tenant_id": tenant_id})
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Factura no encontrada")
    return invoice


async def _allocate_ncf(tenant_id, ncf_type: str) -> Tuple[str, str]:
    """Toma el siguiente NCF de forma ATÓMICA (sin duplicados ni saltos concurrentes)."""
    now = utcnow()
    collection = raw_collection(NCFSequence)
    doc = await collection.find_one_and_update(
        {
            "tenant_id": tenant_id,
            "ncf_type": ncf_type,
            "status": NCFStatus.ACTIVE.value,
            "$expr": {"$lt": ["$current", "$range_to"]},
            "$or": [{"expires_on": None}, {"expires_on": {"$gte": now}}],
        },
        {"$inc": {"current": 1}, "$set": {"updated_at": now}},
        sort=[("range_from", 1)],
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No hay una secuencia NCF {} activa y vigente con números disponibles".format(
                ncf_type
            ),
        )
    if doc["current"] >= doc["range_to"]:
        await collection.update_one(
            {"_id": doc["_id"], "current": {"$gte": doc["range_to"]}},
            {"$set": {"status": NCFStatus.EXHAUSTED.value, "updated_at": now}},
        )
    return "{}{:08d}".format(doc["prefix"], doc["current"]), doc["ncf_type"]


def _tax_info(snapshot: Optional[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    tax = (snapshot or {}).get("tax_id") or {}
    number = tax.get("number")
    tax_type = tax.get("type")
    tax_type = getattr(tax_type, "value", tax_type)
    return number, TIPO_ID.get(str(tax_type))


# ---------------------------------------------------------------- Reporte 607
@router.get("/reports/607", response_model=Report607Response)
async def report_607(
    period: str = Query(..., pattern=PERIOD_REGEX),
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Reporte 607 (ventas) del periodo YYYY-MM. Excluye anuladas (van en el 608)."""
    invoices = (
        await Invoice.find(
            {
                "tenant_id": tenant.id,
                "period": period,
                "status": {"$ne": InvoiceStatus.VOIDED.value},
                "ncf": {"$type": "string"},
            }
        )
        .sort("issued_at")
        .to_list()
    )
    rows: List[Report607Row] = []
    totals = ReportTotals()
    for inv in invoices:
        number, tipo_id = _tax_info(inv.client_snapshot)
        retained = inv.totals.itbis_retained + inv.totals.isr_retained
        stamp = inv.issued_at.strftime("%Y%m%d")
        rows.append(
            Report607Row(
                invoice_id=inv.id,
                rnc_cedula=number,
                tipo_identificacion=tipo_id,
                ncf=inv.ncf,
                ncf_modificado=inv.ncf_modified,
                tipo_ingreso=getattr(inv.income_type, "value", inv.income_type),
                fecha_comprobante=stamp,
                fecha_retencion=stamp if retained > 0 else None,
                monto_facturado=inv.totals.subtotal,
                itbis_facturado=inv.totals.itbis,
                itbis_retenido=inv.totals.itbis_retained,
                retencion_renta=inv.totals.isr_retained,
                forma_pago=getattr(inv.payment.method, "value", inv.payment.method),
            )
        )
        totals.count += 1
        totals.monto_total += inv.totals.subtotal
        totals.itbis_total += inv.totals.itbis
        totals.retenciones_total += retained
    return Report607Response(
        period=period, tenant_rnc=tenant.fiscal.rnc, rows=rows, totals=totals
    )


# ------------------------------------------------------------------- facturas
@router.get("", response_model=InvoicePage)
async def list_invoices(
    params: PageParams = Depends(get_page_params),
    flt: InvoiceFilter = Depends(invoice_filter),
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_ROLES)),
):
    query: Dict[str, Any] = {"tenant_id": tenant.id}
    if flt.status:
        query["status"] = flt.status.value
    if flt.client_id:
        query["client_id"] = flt.client_id
    if flt.period:
        query["period"] = flt.period
    if flt.ncf:
        query["ncf"] = flt.ncf.strip().upper()
    issued = date_range_filter(flt.date_from, flt.date_to)
    if issued:
        query["issued_at"] = issued

    total = await Invoice.find(query).count()
    docs = (
        await Invoice.find(query)
        .sort("-issued_at")
        .skip(params.skip)
        .limit(params.page_size)
        .to_list()
    )
    items = [InvoiceOut.model_validate(doc) for doc in docs]
    return InvoicePage.build(items, total, params)


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    data: InvoiceCreate,
    request: Request,
    tenant: Tenant = Depends(require_writable_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    """Emite una factura. Los totales e ITBIS se calculan en el servidor."""
    client_snapshot: Dict[str, Any] = dict(data.client_snapshot or {})
    if data.client_id:
        client = await Client.find_one({"_id": data.client_id, "tenant_id": tenant.id})
        if client is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
        client_snapshot = {
            "name": client.name,
            "email": client.email,
            "phone": client.phone,
            "address": client.address,
            "tax_id": client.tax_id.model_dump(mode="json") if client.tax_id else None,
        }

    contract: Optional[Contract] = None
    if data.contract_id:
        contract = await Contract.find_one({"_id": data.contract_id, "tenant_id": tenant.id})
        if contract is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contrato no encontrado")

    lines: List[InvoiceLine] = []
    subtotal = Decimal("0")
    itbis_total = Decimal("0")
    for line in data.lines:
        base = _q(line.qty * line.unit_price)
        tax = _q(base * line.itbis_rate)
        lines.append(
            InvoiceLine(
                description=line.description,
                ref=line.ref,
                qty=line.qty,
                unit_price=line.unit_price,
                itbis_rate=line.itbis_rate,
                itbis=tax,
                total=base + tax,
            )
        )
        subtotal += base
        itbis_total += tax

    if data.itbis_retained > itbis_total:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El ITBIS retenido no puede superar el ITBIS facturado",
        )

    totals = InvoiceTotals(
        subtotal=subtotal,
        itbis=itbis_total,
        total=subtotal + itbis_total,
        itbis_retained=data.itbis_retained,
        isr_retained=data.isr_retained,
        currency=data.currency,
    )

    ncf: Optional[str] = None
    ncf_type: Optional[str] = None
    if data.ncf_type:
        ncf, ncf_type = await _allocate_ncf(tenant.id, data.ncf_type)

    number = "F-{:06d}".format(await next_counter(tenant.id, "invoice"))
    payment: InvoicePayment = data.payment
    invoice = Invoice(
        tenant_id=tenant.id,
        number=number,
        ncf=ncf,
        ncf_type=ncf_type,
        ncf_modified=data.ncf_modified,
        client_id=data.client_id,
        client_snapshot=client_snapshot,
        contract_id=data.contract_id,
        income_type=data.income_type,
        lines=lines,
        totals=totals,
        payment=payment,
        status=InvoiceStatus.PAID if payment.paid_at else InvoiceStatus.ISSUED,
        issued_at=data.issued_at or utcnow(),
        issued_by=user.id,
    )
    try:
        await invoice.insert()
    except DuplicateKeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Factura duplicada")

    if contract is not None:
        contract.invoice_ids.append(invoice.id)
        await contract.save()

    await write_audit(
        "invoice.create",
        actor_id=user.id,
        tenant_id=tenant.id,
        entity_type="invoice",
        entity_id=invoice.id,
        meta={"number": number, "ncf": ncf},
        request=request,
    )
    return invoice


@router.get("/{invoice_id}", response_model=InvoiceOut)
async def get_invoice(
    invoice_id: PydanticObjectId,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_ROLES)),
):
    return await _get_invoice(tenant.id, invoice_id)


@router.post("/{invoice_id}/pay", response_model=InvoiceOut)
async def pay_invoice(
    invoice_id: PydanticObjectId,
    data: InvoicePaymentUpdate,
    request: Request,
    tenant: Tenant = Depends(require_writable_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    invoice = await _get_invoice(tenant.id, invoice_id)
    if invoice.status != InvoiceStatus.ISSUED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Solo se pueden cobrar facturas en estado 'issued'",
        )
    invoice.payment = InvoicePayment(
        method=data.method,
        gateway_id=data.gateway_id,
        paid_at=data.paid_at or utcnow(),
    )
    invoice.status = InvoiceStatus.PAID
    await invoice.save()
    await write_audit(
        "invoice.pay",
        actor_id=user.id,
        tenant_id=tenant.id,
        entity_type="invoice",
        entity_id=invoice.id,
        request=request,
    )
    return invoice


@router.post("/{invoice_id}/void", response_model=InvoiceOut)
async def void_invoice(
    invoice_id: PydanticObjectId,
    data: InvoiceVoidRequest,
    request: Request,
    tenant: Tenant = Depends(require_writable_tenant),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Anula una factura. El NCF queda consumido (se reporta como anulado, formato 608)."""
    invoice = await _get_invoice(tenant.id, invoice_id)
    if invoice.status == InvoiceStatus.VOIDED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La factura ya está anulada")
    invoice.status = InvoiceStatus.VOIDED
    invoice.voided = InvoiceVoid(reason=data.reason, by=user.id)
    await invoice.save()
    await write_audit(
        "invoice.void",
        actor_id=user.id,
        tenant_id=tenant.id,
        entity_type="invoice",
        entity_id=invoice.id,
        meta={"number": invoice.number, "ncf": invoice.ncf, "reason": data.reason},
        request=request,
    )
    return invoice
