from decimal import Decimal
from typing import Any, Dict, List, Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo.errors import DuplicateKeyError

from app.core.db_utils import d128
from app.core.deps import (
    STAFF_ROLES,
    STAFF_WRITE_ROLES,
    build_model,
    get_current_tenant,
    get_page_params,
    require_roles,
)
from app.models.enums import Lifecycle, PropertyKind, UnitAvailability
from app.models.property import ProjectDetails, Property, UnitsSummary
from app.models.tenant import Tenant
from app.models.unit import Unit
from app.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.unit import (
    UnitBulkCreate,
    UnitCreate,
    UnitFilter,
    UnitOut,
    UnitStatusUpdate,
    UnitUpdate,
)

router = APIRouter(tags=["units"])

UnitPage = Page[UnitOut]


def unit_filter(
    availability: Optional[UnitAvailability] = Query(None),
    lifecycle: Optional[Lifecycle] = Query(None),
    tower: Optional[str] = Query(None, max_length=30),
    floor: Optional[int] = Query(None),
    min_price: Optional[Decimal] = Query(None, ge=0),
    max_price: Optional[Decimal] = Query(None, ge=0),
    min_bedrooms: Optional[int] = Query(None, ge=0),
) -> UnitFilter:
    return build_model(
        UnitFilter,
        availability=availability,
        lifecycle=lifecycle,
        tower=tower,
        floor=floor,
        min_price=min_price,
        max_price=max_price,
        min_bedrooms=min_bedrooms,
    )


async def _get_project(tenant_id, property_id: PydanticObjectId) -> Property:
    prop = await Property.find_one({"_id": property_id, "tenant_id": tenant_id})
    if prop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    if prop.kind != PropertyKind.PROJECT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo los proyectos/torres contienen unidades",
        )
    return prop


async def _get_unit(tenant_id, unit_id: PydanticObjectId) -> Unit:
    unit = await Unit.find_one({"_id": unit_id, "tenant_id": tenant_id})
    if unit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unidad no encontrada")
    return unit


async def _refresh_summary(tenant_id, property_id: PydanticObjectId) -> None:
    """Recalcula el resumen denormalizado de unidades del proyecto."""
    prop = await Property.find_one({"_id": property_id, "tenant_id": tenant_id})
    if prop is None:
        return
    units = await Unit.find({"tenant_id": tenant_id, "property_id": property_id}).to_list()
    summary = UnitsSummary()
    prices: List[Decimal] = []
    for unit in units:
        if unit.availability == UnitAvailability.AVAILABLE:
            summary.available += 1
        elif unit.availability == UnitAvailability.RESERVED:
            summary.reserved += 1
        elif unit.availability == UnitAvailability.SOLD:
            summary.sold += 1
        prices.append(unit.price)
    summary.price_min = min(prices) if prices else None
    summary.price_max = max(prices) if prices else None
    if prop.project is None:
        prop.project = ProjectDetails()
    prop.project.units_summary = summary
    prop.project.total_units = max(prop.project.total_units, len(units))
    await prop.save()


# ------------------------------------------------------ unidades de un proyecto
@router.get("/properties/{property_id}/units", response_model=UnitPage)
async def list_units(
    property_id: PydanticObjectId,
    params: PageParams = Depends(get_page_params),
    flt: UnitFilter = Depends(unit_filter),
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_ROLES)),
):
    await _get_project(tenant.id, property_id)
    query: Dict[str, Any] = {"tenant_id": tenant.id, "property_id": property_id}
    if flt.availability:
        query["availability"] = flt.availability.value
    if flt.lifecycle:
        query["lifecycle"] = flt.lifecycle.value
    if flt.tower:
        query["tower"] = flt.tower
    if flt.floor is not None:
        query["floor"] = flt.floor
    if flt.min_bedrooms is not None:
        query["bedrooms"] = {"$gte": flt.min_bedrooms}
    price_range: Dict[str, Any] = {}
    if flt.min_price is not None:
        price_range["$gte"] = d128(flt.min_price)
    if flt.max_price is not None:
        price_range["$lte"] = d128(flt.max_price)
    if price_range:
        query["price"] = price_range

    total = await Unit.find(query).count()
    docs = (
        await Unit.find(query)
        .sort("tower", "floor", "code")
        .skip(params.skip)
        .limit(params.page_size)
        .to_list()
    )
    items = [UnitOut.model_validate(doc) for doc in docs]
    return UnitPage.build(items, total, params)


@router.post(
    "/properties/{property_id}/units",
    response_model=UnitOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_unit(
    property_id: PydanticObjectId,
    data: UnitCreate,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    await _get_project(tenant.id, property_id)
    unit = Unit(tenant_id=tenant.id, property_id=property_id, **data.model_dump())
    try:
        await unit.insert()
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una unidad con el código {}".format(data.code),
        )
    await _refresh_summary(tenant.id, property_id)
    return unit


@router.post(
    "/properties/{property_id}/units/bulk",
    response_model=List[UnitOut],
    status_code=status.HTTP_201_CREATED,
)
async def create_units_bulk(
    property_id: PydanticObjectId,
    data: UnitBulkCreate,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    """Carga masiva de unidades (ej. todos los apartamentos de una torre)."""
    await _get_project(tenant.id, property_id)
    codes = [u.code for u in data.units]
    existing = await Unit.find(
        {"tenant_id": tenant.id, "property_id": property_id, "code": {"$in": codes}}
    ).to_list()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Códigos ya existentes: {}".format(", ".join(sorted(u.code for u in existing))),
        )
    created: List[Unit] = []
    for item in data.units:
        unit = Unit(tenant_id=tenant.id, property_id=property_id, **item.model_dump())
        try:
            await unit.insert()
        except DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Código duplicado: {}".format(item.code),
            )
        created.append(unit)
    await _refresh_summary(tenant.id, property_id)
    return created


# ------------------------------------------------------------ unidad individual
@router.get("/units/{unit_id}", response_model=UnitOut)
async def get_unit(
    unit_id: PydanticObjectId,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_ROLES)),
):
    return await _get_unit(tenant.id, unit_id)


@router.patch("/units/{unit_id}", response_model=UnitOut)
async def update_unit(
    unit_id: PydanticObjectId,
    data: UnitUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    unit = await _get_unit(tenant.id, unit_id)
    nullable = {"label", "floor", "tower", "bedrooms", "bathrooms", "area_m2", "parking", "floor_plan_media_id"}
    for field in data.model_fields_set:
        value = getattr(data, field)
        if value is None and field not in nullable:
            continue
        setattr(unit, field, value)
    try:
        await unit.save()
    except DuplicateKeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El código de unidad ya existe")
    if {"price", "code"} & data.model_fields_set:
        await _refresh_summary(tenant.id, unit.property_id)
    return unit


@router.patch("/units/{unit_id}/status", response_model=UnitOut)
async def update_unit_status(
    unit_id: PydanticObjectId,
    data: UnitStatusUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    """Cambio manual de disponibilidad y/o ciclo de vida de la unidad."""
    unit = await _get_unit(tenant.id, unit_id)
    if data.availability is not None:
        unit.availability = data.availability
        if data.availability == UnitAvailability.AVAILABLE:
            unit.reserved_by_request_id = None
    if data.lifecycle is not None:
        unit.lifecycle = data.lifecycle
    await unit.save()
    await _refresh_summary(tenant.id, unit.property_id)
    return unit


@router.delete("/units/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unit(
    unit_id: PydanticObjectId,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    unit = await _get_unit(tenant.id, unit_id)
    if unit.availability != UnitAvailability.AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar una unidad reservada o vendida",
        )
    property_id = unit.property_id
    await unit.delete()
    await _refresh_summary(tenant.id, property_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
