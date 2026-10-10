import re
from datetime import timedelta
from typing import Any, Dict, Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core import security
from app.core.audit import write_audit
from app.core.deps import get_current_super_admin, get_page_params
from app.core.provisioning import provision_tenant
from app.models.base import ensure_utc, utcnow
from app.models.enums import AuditActorType, LicenseStatus, SubscriptionStatus
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.models.token import LicenseToken
from app.schemas.common import Page, PageParams
from app.schemas.license import (
    LicenseBatchCreatedOut,
    LicenseCreate,
    LicenseCreatedOut,
    LicenseOut,
    LicenseRevokeRequest,
)
from app.schemas.tenant import (
    SubscriptionAdminUpdate,
    TenantCreate,
    TenantListItem,
    TenantOut,
)

router = APIRouter(prefix="/admin", tags=["super-admin"])

TenantPage = Page[TenantListItem]
LicensePage = Page[LicenseOut]


async def _get_tenant(tenant_id: PydanticObjectId) -> Tenant:
    tenant = await Tenant.get(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agencia no encontrada")
    return tenant


# -------------------------------------------------------------------- tenants
@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    data: TenantCreate,
    request: Request,
    admin: SuperAdmin = Depends(get_current_super_admin),
):
    tenant, _user = await provision_tenant(
        slug=data.slug,
        name=data.name,
        owner_email=data.owner_email,
        owner_full_name=data.owner_full_name,
        password=data.owner_password,
        plan=data.plan,
        duration_days=data.duration_days,
        limits=data.limits,
    )
    await write_audit(
        "admin.tenant.create",
        actor_type=AuditActorType.SUPER_ADMIN,
        actor_id=admin.id,
        tenant_id=tenant.id,
        entity_type="tenant",
        entity_id=tenant.id,
        request=request,
    )
    return TenantOut.from_tenant(tenant)


@router.get("/tenants", response_model=TenantPage)
async def list_tenants(
    q: Optional[str] = Query(None, max_length=80),
    subscription_status: Optional[SubscriptionStatus] = Query(None),
    params: PageParams = Depends(get_page_params),
    admin: SuperAdmin = Depends(get_current_super_admin),
):
    query: Dict[str, Any] = {}
    if q:
        pattern = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"name": pattern}, {"slug": pattern}]
    if subscription_status:
        query["subscription.status"] = subscription_status.value
    total = await Tenant.find(query).count()
    docs = (
        await Tenant.find(query)
        .sort("-created_at")
        .skip(params.skip)
        .limit(params.page_size)
        .to_list()
    )
    items = [TenantListItem.model_validate(doc) for doc in docs]
    return TenantPage.build(items, total, params)


@router.get("/tenants/{tenant_id}", response_model=TenantOut)
async def get_tenant(
    tenant_id: PydanticObjectId,
    admin: SuperAdmin = Depends(get_current_super_admin),
):
    return TenantOut.from_tenant(await _get_tenant(tenant_id))


@router.patch("/tenants/{tenant_id}/subscription", response_model=TenantOut)
async def update_subscription(
    tenant_id: PydanticObjectId,
    data: SubscriptionAdminUpdate,
    request: Request,
    admin: SuperAdmin = Depends(get_current_super_admin),
):
    tenant = await _get_tenant(tenant_id)
    sub = tenant.subscription
    now = utcnow()

    if data.plan is not None:
        sub.plan = data.plan
    if data.expires_at is not None:
        sub.expires_at = ensure_utc(data.expires_at)
    if data.extend_days is not None:
        base = max(now, ensure_utc(sub.expires_at) or now)
        sub.expires_at = base + timedelta(days=data.extend_days)
        if sub.status in (SubscriptionStatus.EXPIRED, SubscriptionStatus.SUSPENDED):
            sub.status = SubscriptionStatus.ACTIVE
    if data.status is not None:
        sub.status = data.status
    if data.limits is not None:
        tenant.limits = data.limits

    await tenant.save()
    await write_audit(
        "admin.subscription.update",
        actor_type=AuditActorType.SUPER_ADMIN,
        actor_id=admin.id,
        tenant_id=tenant.id,
        entity_type="tenant",
        entity_id=tenant.id,
        meta={"fields": sorted(data.model_fields_set)},
        request=request,
    )
    return TenantOut.from_tenant(tenant)


@router.post("/tenants/{tenant_id}/domains/{host}/verify", response_model=TenantOut)
async def force_verify_domain(
    tenant_id: PydanticObjectId,
    host: str,
    request: Request,
    admin: SuperAdmin = Depends(get_current_super_admin),
):
    """Verificación manual de un dominio por el Super Admin."""
    tenant = await _get_tenant(tenant_id)
    host = host.strip().lower()
    for entry in tenant.domains:
        if entry.host == host:
            entry.verified = True
            await tenant.save()
            await write_audit(
                "admin.domain.verify",
                actor_type=AuditActorType.SUPER_ADMIN,
                actor_id=admin.id,
                tenant_id=tenant.id,
                entity_type="tenant",
                entity_id=tenant.id,
                meta={"host": host},
                request=request,
            )
            return TenantOut.from_tenant(tenant)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dominio no encontrado")


# ------------------------------------------------------------------- licencias
@router.post("/licenses", response_model=LicenseBatchCreatedOut, status_code=status.HTTP_201_CREATED)
async def create_licenses(
    data: LicenseCreate,
    request: Request,
    admin: SuperAdmin = Depends(get_current_super_admin),
):
    """Genera tokens de activación. El token en claro solo se devuelve en esta respuesta."""
    items = []
    for _ in range(data.quantity):
        raw, prefix, token_hash = security.generate_license_token()
        license_doc = LicenseToken(
            token_hash=token_hash,
            token_prefix=prefix,
            plan=data.plan,
            duration_days=data.duration_days,
            limits_override=data.limits_override,
            created_by=admin.id,
            valid_until_redeem=ensure_utc(data.valid_until_redeem),
            payment_ref=data.payment_ref,
            notes=data.notes,
        )
        await license_doc.insert()
        base = LicenseOut.model_validate(license_doc).model_dump()
        items.append(LicenseCreatedOut(**base, token=raw))
    await write_audit(
        "admin.license.create",
        actor_type=AuditActorType.SUPER_ADMIN,
        actor_id=admin.id,
        meta={"plan": data.plan.value, "quantity": data.quantity},
        request=request,
    )
    return LicenseBatchCreatedOut(items=items)


@router.get("/licenses", response_model=LicensePage)
async def list_licenses(
    license_status: Optional[LicenseStatus] = Query(None),
    tenant_id: Optional[PydanticObjectId] = Query(None),
    params: PageParams = Depends(get_page_params),
    admin: SuperAdmin = Depends(get_current_super_admin),
):
    query: Dict[str, Any] = {}
    if license_status:
        query["status"] = license_status.value
    if tenant_id:
        query["redeemed_by_tenant_id"] = tenant_id
    total = await LicenseToken.find(query).count()
    docs = (
        await LicenseToken.find(query)
        .sort("-created_at")
        .skip(params.skip)
        .limit(params.page_size)
        .to_list()
    )
    items = [LicenseOut.model_validate(doc) for doc in docs]
    return LicensePage.build(items, total, params)


@router.post("/licenses/{license_id}/revoke", response_model=LicenseOut)
async def revoke_license(
    license_id: PydanticObjectId,
    data: LicenseRevokeRequest,
    request: Request,
    admin: SuperAdmin = Depends(get_current_super_admin),
):
    license_doc = await LicenseToken.get(license_id)
    if license_doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Licencia no encontrada")
    if license_doc.status != LicenseStatus.UNUSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Solo se pueden revocar licencias sin usar",
        )
    license_doc.status = LicenseStatus.REVOKED
    if data.reason:
        license_doc.notes = ((license_doc.notes or "") + " | Revocada: " + data.reason).strip(" |")
    await license_doc.save()
    await write_audit(
        "admin.license.revoke",
        actor_type=AuditActorType.SUPER_ADMIN,
        actor_id=admin.id,
        entity_type="license",
        entity_id=license_doc.id,
        request=request,
    )
    return license_doc
