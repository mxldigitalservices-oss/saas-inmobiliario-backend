from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pymongo.errors import DuplicateKeyError

from app.core.audit import write_audit
from app.core.db_utils import date_range_filter
from app.core.deps import (
    ADMIN_ROLES,
    build_model,
    get_current_tenant,
    get_page_params,
    require_roles,
)
from app.models.base import period_of, utcnow
from app.models.enums import ExpenseStatus, ExpenseType
from app.models.expenses import Expense
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.common import PERIOD_REGEX, Page, PageParams
from app.schemas.expense import (
    ExpenseCreate,
    ExpenseFilter,
    ExpenseOut,
    ExpenseUpdate,
    ExpenseVoidRequest,
)
from app.schemas.report import Report606Response, Report606Row, ReportTotals

router = APIRouter(prefix="/expenses", tags=["expenses"])

ExpensePage = Page[ExpenseOut]
TIPO_ID = {"rnc": "1", "cedula": "2", "passport": "3"}
NULLABLE_FIELDS = {"description", "category", "ncf", "ncf_modified", "payment_date", "attachment_media_id"}


def expense_filter(
    status_: Optional[ExpenseStatus] = Query(None, alias="status"),
    expense_type: Optional[ExpenseType] = Query(None),
    category: Optional[str] = Query(None, max_length=80),
    supplier_tax_id: Optional[str] = Query(None, max_length=30),
    period: Optional[str] = Query(None, pattern=PERIOD_REGEX),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
) -> ExpenseFilter:
    return build_model(
        ExpenseFilter,
        status=status_,
        expense_type=expense_type,
        category=category,
        supplier_tax_id=supplier_tax_id,
        period=period,
        date_from=date_from,
        date_to=date_to,
    )


async def _get_expense(tenant_id, expense_id: PydanticObjectId) -> Expense:
    expense = await Expense.find_one({"_id": expense_id, "tenant_id": tenant_id})
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gasto no encontrado")
    return expense


def _value(item: Any) -> Any:
    return getattr(item, "value", item)


# ---------------------------------------------------------------- Reporte 606
@router.get("/reports/606", response_model=Report606Response)
async def report_606(
    period: str = Query(..., pattern=PERIOD_REGEX),
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Reporte 606 (compras y gastos) del periodo YYYY-MM. Excluye gastos anulados."""
    expenses = (
        await Expense.find(
            {
                "tenant_id": tenant.id,
                "period": period,
                "status": ExpenseStatus.RECORDED.value,
            }
        )
        .sort("receipt_date")
        .to_list()
    )
    rows: List[Report606Row] = []
    totals = ReportTotals()
    for exp in expenses:
        a = exp.amounts
        rows.append(
            Report606Row(
                expense_id=exp.id,
                rnc_cedula=exp.supplier.tax_id,
                tipo_identificacion=TIPO_ID.get(str(_value(exp.supplier.tax_id_type))),
                tipo_bienes_servicios=_value(exp.expense_type),
                ncf=exp.ncf,
                ncf_modificado=exp.ncf_modified,
                fecha_comprobante=exp.receipt_date.strftime("%Y%m%d"),
                fecha_pago=exp.payment_date.strftime("%Y%m%d") if exp.payment_date else None,
                monto_servicios=a.services_amount,
                monto_bienes=a.goods_amount,
                total_facturado=a.total_amount,
                itbis_facturado=a.itbis_billed,
                itbis_retenido=a.itbis_withheld,
                itbis_proporcionalidad=a.itbis_proportionality,
                itbis_costo=a.itbis_to_cost,
                itbis_adelantar=a.itbis_to_advance,
                itbis_percibido=a.itbis_perceived,
                tipo_retencion_isr=a.isr_withholding_type,
                retencion_renta=a.isr_withheld,
                isr_percibido=a.isr_perceived,
                impuesto_selectivo=a.selective_tax,
                otros_impuestos=a.other_taxes,
                propina_legal=a.legal_tip,
                forma_pago=_value(exp.payment_form),
            )
        )
        totals.count += 1
        totals.monto_total += a.total_amount
        totals.itbis_total += a.itbis_billed
        totals.retenciones_total += a.itbis_withheld + a.isr_withheld
    return Report606Response(
        period=period, tenant_rnc=tenant.fiscal.rnc, rows=rows, totals=totals
    )


# --------------------------------------------------------------------- gastos
@router.get("", response_model=ExpensePage)
async def list_expenses(
    params: PageParams = Depends(get_page_params),
    flt: ExpenseFilter = Depends(expense_filter),
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    query: Dict[str, Any] = {"tenant_id": tenant.id}
    if flt.status:
        query["status"] = flt.status.value
    if flt.expense_type:
        query["expense_type"] = flt.expense_type.value
    if flt.category:
        query["category"] = flt.category
    if flt.supplier_tax_id:
        query["supplier.tax_id"] = flt.supplier_tax_id
    if flt.period:
        query["period"] = flt.period
    received = date_range_filter(flt.date_from, flt.date_to)
    if received:
        query["receipt_date"] = received

    total = await Expense.find(query).count()
    docs = (
        await Expense.find(query)
        .sort("-receipt_date")
        .skip(params.skip)
        .limit(params.page_size)
        .to_list()
    )
    items = [ExpenseOut.model_validate(doc) for doc in docs]
    return ExpensePage.build(items, total, params)


@router.post("", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
async def create_expense(
    data: ExpenseCreate,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    expense = Expense(
        tenant_id=tenant.id,
        supplier=data.supplier,
        expense_type=data.expense_type,
        description=data.description,
        category=data.category,
        ncf=data.ncf,
        ncf_modified=data.ncf_modified,
        receipt_date=data.receipt_date or utcnow(),
        payment_date=data.payment_date,
        payment_form=data.payment_form,
        amounts=data.amounts,
        attachment_media_id=data.attachment_media_id,
        created_by=user.id,
    )
    try:
        await expense.insert()
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un gasto con ese NCF para el mismo proveedor",
        )
    await write_audit(
        "expense.create",
        actor_id=user.id,
        tenant_id=tenant.id,
        entity_type="expense",
        entity_id=expense.id,
        meta={"ncf": expense.ncf},
        request=request,
    )
    return expense


@router.get("/{expense_id}", response_model=ExpenseOut)
async def get_expense(
    expense_id: PydanticObjectId,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    return await _get_expense(tenant.id, expense_id)


@router.patch("/{expense_id}", response_model=ExpenseOut)
async def update_expense(
    expense_id: PydanticObjectId,
    data: ExpenseUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    expense = await _get_expense(tenant.id, expense_id)
    if expense.status == ExpenseStatus.VOIDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="No se puede modificar un gasto anulado"
        )

    for field in data.model_fields_set:
        value = getattr(data, field)
        if value is None and field not in NULLABLE_FIELDS:
            continue
        setattr(expense, field, value)

    if "amounts" in data.model_fields_set and expense.amounts.total_amount == 0:
        expense.amounts.total_amount = (
            expense.amounts.services_amount + expense.amounts.goods_amount
        )
    if "receipt_date" in data.model_fields_set and data.receipt_date is not None:
        expense.period = period_of(expense.receipt_date)

    try:
        await expense.save()
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un gasto con ese NCF para el mismo proveedor",
        )
    return expense


@router.post("/{expense_id}/void", response_model=ExpenseOut)
async def void_expense(
    expense_id: PydanticObjectId,
    data: ExpenseVoidRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    expense = await _get_expense(tenant.id, expense_id)
    if expense.status == ExpenseStatus.VOIDED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El gasto ya está anulado")
    expense.status = ExpenseStatus.VOIDED
    suffix = "[ANULADO: {}]".format(data.reason)
    expense.description = "{} {}".format(expense.description or "", suffix).strip()
    await expense.save()
    await write_audit(
        "expense.void",
        actor_id=user.id,
        tenant_id=tenant.id,
        entity_type="expense",
        entity_id=expense.id,
        meta={"reason": data.reason},
        request=request,
    )
    return expense
