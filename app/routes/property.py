import re
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
    resolve_tenant,
)
from app.models.enums import (
    Lifecycle,
    OperationType,
    PropertyKind,
    PropertyType,
    PublishStatus,
)
from app.models.property import Property
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.common import Page, PageParams, slugify
from app.schemas.property import (
    PropertyCreate,
    PropertyFilter,
    PropertyListItem,
    PropertyOut,
    PropertyUpdate,
)

router = APIRouter(prefix="/properties", tags=["properties"])

PropertyPage = Page[PropertyListItem]
NULLABLE_FIELDS = {"description", "cover_media_id", "agent_id"}


# ------------------------------------------------------------------ filtros
def property_filter(
    q: Optional[str] = Query(None, max_length=120),
    kind: Optional[PropertyKind] = Query(None),
    operation: Optional[OperationType] = Query(None),
    type: Optional[PropertyType] = Query(None),
    status_: Optional[PublishStatus] = Query(None, alias="status"),
    lifecycle: Optional[Lifecycle] = Query(None),
    city: Optional[str] = Query(None, max_length=80),
    sector: Optional[str] = Query(None, max_length=80),
    min_price: Optional[Decimal] = Query(None, ge=0),
    max_price: Optional[Decimal] = Query(None, ge=0),
    min_bedrooms: Optional[int] = Query(None, ge=0),
    agent_id: Optional[PydanticObjectId] = Query(None),
    near_lng: Optional[float] = Query(None),
    near_lat: Optional[float] = Query(None),
    radius_km: Optional[float] = Query(None),
) -> PropertyFilter:
    return build_model(
        PropertyFilter,
        q=q,
        kind=kind,
        operation=operation,
        type=type,
        status=status_,
        lifecycle=lifecycle,
        city=city,
        sector=sector,
        min_price=min_price,
        max_price=max_price,
        min_bedrooms=min_bedrooms,
        agent_id=agent_id,
        near_lng=near_lng,
        near_lat=near_lat,
        radius_km=radius_km,
    )


def _ci_exact(value: str) -> Dict[str, str]:
    return {"$regex": "^{}$".format(re.escape(value.strip())), "$options": "i"}


def _build_query(tenant_id, f: PropertyFilter, *, public: bool = False) -> Dict[str, Any]:
    query: Dict[str, Any] = {"tenant_id": tenant_id}
    and_conditions: List[Dict[str, Any]] = []

    if public:
        query["status"] = PublishStatus.PUBLISHED.value
    elif f.status is not None:
        query["status"] = f.status.value
    else:
        query["status"] = {"$ne": PublishStatus.ARCHIVED.value}

    if f.kind:
        query["kind"] = f.kind.value
    if f.operation:
        query["operation"] = {"$in": [f.operation.value, OperationType.BOTH.value]}
    if f.type:
        query["type"] = f.type.value
    if f.lifecycle:
        query["lifecycle"] = f.lifecycle.value
    if f.agent_id:
        query["agent_id"] = f.agent_id
    if f.city:
        query["location.city"] = _ci_exact(f.city)
    if f.sector:
        query["location.sector"] = _ci_exact(f.sector)
    if f.q:
        query["$text"] = {"$search": f.q}

    if f.min_price is not None or f.max_price is not None:
        single_range: Dict[str, Any] = {}
        project_conditions: List[Dict[str, Any]] = []
        if f.min_price is not None:
            low = d128(f.min_price)
            single_range["$gte"] = low
            project_conditions.append({"project.units_summary.price_max": {"$gte": low}})
        if f.max_price is not None:
            high = d128(f.max_price)
            single_range["$lte"] = high
            project_conditions.append({"project.units_summary.price_min": {"$lte": high}})
        and_conditions.append(
            {"$or": [{"single.price": single_range}, {"$and": project_conditions}]}
        )

    if f.min_bedrooms is not None:
        and_conditions.append(
            {
                "$or": [
                    {"single.bedrooms": {"$gte": f.min_bedrooms}},
                    {"kind": PropertyKind.PROJECT.value},
                ]
            }
        )

    if f.near_lng is not None and f.near_lat is not None and f.radius_km is not None:
        query["location.geo"] = {
            "$geoWithin": {"$centerSphere": [[f.near_lng, f.near_lat], f.radius_km / 6378.1]}
        }

    if and_conditions:
        query["$and"] = and_conditions
    return query


async def _paginate(query: Dict[str, Any], params: PageParams) -> PropertyPage:
    total = await Property.find(query).count()
    docs = (
        await Property.find(query)
        .sort("-created_at")
        .skip(params.skip)
        .limit(params.page_size)
        .to_list()
    )
    items = [PropertyListItem.model_validate(doc) for doc in docs]
    return PropertyPage.build(items, total, params)


async def _get_property(tenant_id, property_id: PydanticObjectId) -> Property:
    prop = await Property.find_one({"_id": property_id, "tenant_id": tenant_id})
    if prop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada")
    return prop


async def _slug_taken(tenant_id, slug: str, exclude_id: Optional[PydanticObjectId] = None) -> bool:
    query: Dict[str, Any] = {"tenant_id": tenant_id, "slug": slug}
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    return await Property.find_one(query) is not None


async def _unique_slug(tenant_id, base: str) -> str:
    base = slugify(base)[:100]
    candidate = base
    for n in range(2, 60):
        if not await _slug_taken(tenant_id, candidate):
            return candidate
        candidate = "{}-{}".format(base, n)
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No se pudo generar un slug único")


# ------------------------------------------------------- catálogo público (Host)
@router.get("/public", response_model=PropertyPage)
async def list_public_properties(
    params: PageParams = Depends(get_page_params),
    flt: PropertyFilter = Depends(property_filter),
    tenant: Tenant = Depends(resolve_tenant),
):
    """Propiedades publicadas de la agencia identificada por el Host header."""
    return await _paginate(_build_query(tenant.id, flt, public=True), params)


@router.get("/public/{slug}", response_model=PropertyOut)
async def get_public_property(slug: str, tenant: Tenant = Depends(resolve_tenant)):
    prop = await Property.find_one(
        {
            "tenant_id": tenant.id,
            "slug": slug.strip().lower(),
            "status": PublishStatus.PUBLISHED.value,
        }
    )
    if prop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada")
    return prop


# ---------------------------------------------------------------- panel interno
@router.get("", response_model=PropertyPage)
async def list_properties(
    params: PageParams = Depends(get_page_params),
    flt: PropertyFilter = Depends(property_filter),
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_ROLES)),
):
    return await _paginate(_build_query(tenant.id, flt), params)


@router.post("", response_model=PropertyOut, status_code=status.HTTP_201_CREATED)
async def create_property(
    data: PropertyCreate,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    active = await Property.find(
        {"tenant_id": tenant.id, "status": {"$ne": PublishStatus.ARCHIVED.value}}
    ).count()
    if active >= tenant.limits.max_properties:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Alcanzaste el límite de {} propiedades de tu plan".format(
                tenant.limits.max_properties
            ),
        )

    if data.slug:
        slug = data.slug
        if await _slug_taken(tenant.id, slug):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El slug ya existe")
    else:
        slug = await _unique_slug(tenant.id, data.title)

    payload = data.model_dump(exclude={"slug"})
    prop = Property(tenant_id=tenant.id, slug=slug, **payload)
    if prop.agent_id is None:
        prop.agent_id = user.id
    try:
        await prop.insert()
    except DuplicateKeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El slug ya existe")
    return prop


@router.get("/{property_id}", response_model=PropertyOut)
async def get_property(
    property_id: PydanticObjectId,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_ROLES)),
):
    return await _get_property(tenant.id, property_id)


@router.patch("/{property_id}", response_model=PropertyOut)
async def update_property(
    property_id: PydanticObjectId,
    data: PropertyUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    prop = await _get_property(tenant.id, property_id)

    if "single" in data.model_fields_set and prop.kind != PropertyKind.SINGLE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'single' solo aplica a propiedades individuales",
        )
    if "project" in data.model_fields_set and prop.kind != PropertyKind.PROJECT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'project' solo aplica a proyectos",
        )
    if "slug" in data.model_fields_set and data.slug and data.slug != prop.slug:
        if await _slug_taken(tenant.id, data.slug, exclude_id=prop.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El slug ya existe")

    for field in data.model_fields_set:
        value = getattr(data, field)
        if value is None and field not in NULLABLE_FIELDS:
            continue
        setattr(prop, field, value)

    try:
        await prop.save()
    except DuplicateKeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El slug ya existe")
    return prop


@router.post("/{property_id}/publish", response_model=PropertyOut)
async def publish_property(
    property_id: PydanticObjectId,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    prop = await _get_property(tenant.id, property_id)
    prop.status = PublishStatus.PUBLISHED
    await prop.save()
    return prop


@router.post("/{property_id}/unpublish", response_model=PropertyOut)
async def unpublish_property(
    property_id: PydanticObjectId,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    prop = await _get_property(tenant.id, property_id)
    prop.status = PublishStatus.DRAFT
    await prop.save()
    return prop


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_property(
    property_id: PydanticObjectId,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    """Borrado lógico: la propiedad pasa a 'archived' (conserva historial de ventas)."""
    prop = await _get_property(tenant.id, property_id)
    prop.status = PublishStatus.ARCHIVED
    await prop.save()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
