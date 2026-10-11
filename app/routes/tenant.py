import secrets
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pymongo.errors import DuplicateKeyError
from starlette.concurrency import run_in_threadpool

from app.core.audit import write_audit
from app.core.config import settings
from app.core.deps import (
    ADMIN_ROLES,
    get_current_tenant,
    require_roles,
    resolve_public_tenant,
)
from app.core.licensing import redeem_license
from app.models.media import Media
from app.models.tenant import DomainEntry, Tenant
from app.models.user import User
from app.schemas.license import LicenseRedeemOut, LicenseRedeemRequest
from app.schemas.tenant import (
    DomainAddRequest,
    DomainOut,
    SubscriptionStatusOut,
    TenantOut,
    TenantPublicOut,
    TenantUpdate,
)

router = APIRouter(prefix="/tenants", tags=["tenants"])

MAX_DOMAINS = 5
DNS_VERIFY_PREFIX = "_inmo-verify"


def _txt_matches(host: str, token: str) -> bool:
    """Verifica el TXT _inmo-verify.{host} == token (requiere dnspython)."""
    try:
        import dns.resolver  # type: ignore
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Verificación DNS automática no disponible en este servidor",
        )
    try:
        answers = dns.resolver.resolve("{}.{}".format(DNS_VERIFY_PREFIX, host), "TXT")
    except Exception:
        return False
    for rdata in answers:
        text = "".join(
            part.decode("utf-8") if isinstance(part, bytes) else str(part)
            for part in rdata.strings
        )
        if text.strip() == token:
            return True
    return False


def _find_domain(tenant: Tenant, host: str) -> DomainEntry:
    host = host.strip().lower()
    for entry in tenant.domains:
        if entry.host == host:
            return entry
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dominio no encontrado")


@router.get("/public", response_model=TenantPublicOut)
async def public_tenant(tenant: Tenant = Depends(resolve_public_tenant)):
    """Datos públicos de la agencia (sitio de marca blanca): por Host o por ?agency=<slug>."""
    out = TenantPublicOut.model_validate(tenant)
    logo_id = tenant.branding.logo_media_id
    if logo_id is not None:
        logo = await Media.find_one({"_id": logo_id, "tenant_id": tenant.id})
        if logo is not None:
            out.logo_url = logo.storage.thumb_url or logo.storage.url
    return out


@router.get("/me", response_model=TenantOut)
async def get_my_tenant(
    tenant: Tenant = Depends(get_current_tenant),
):
    return TenantOut.from_tenant(tenant)


@router.patch("/me", response_model=TenantOut)
async def update_my_tenant(
    data: TenantUpdate,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    for field in data.model_fields_set:
        value = getattr(data, field)
        if value is not None:
            setattr(tenant, field, value)
    await tenant.save()
    await write_audit(
        "tenant.update",
        actor_id=user.id,
        tenant_id=tenant.id,
        entity_type="tenant",
        entity_id=tenant.id,
        meta={"fields": sorted(data.model_fields_set)},
        request=request,
    )
    return TenantOut.from_tenant(tenant)


@router.get("/me/subscription", response_model=SubscriptionStatusOut)
async def my_subscription(tenant: Tenant = Depends(get_current_tenant)):
    return SubscriptionStatusOut.from_tenant(tenant)


@router.post("/me/license/redeem", response_model=LicenseRedeemOut)
async def redeem_my_license(
    data: LicenseRedeemRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    tenant = await redeem_license(tenant, data.token)
    await write_audit(
        "license.redeem",
        actor_id=user.id,
        tenant_id=tenant.id,
        entity_type="tenant",
        entity_id=tenant.id,
        meta={"token_prefix": data.token.strip().upper()[:8]},
        request=request,
    )
    return LicenseRedeemOut(subscription=tenant.subscription, read_only=tenant.is_read_only())


# ---------------------------------------------------------------- dominios propios
@router.get("/me/domains", response_model=List[DomainOut])
async def list_domains(
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    return tenant.domains


@router.post("/me/domains", response_model=DomainOut, status_code=status.HTTP_201_CREATED)
async def add_domain(
    data: DomainAddRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Agrega un dominio propio. Debe verificarse con un registro TXT antes de usarse."""
    if len(tenant.domains) >= MAX_DOMAINS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Máximo {} dominios por agencia".format(MAX_DOMAINS),
        )
    base = settings.BASE_DOMAIN
    if base and (data.host == base or data.host.endswith("." + base)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ese dominio pertenece a la plataforma",
        )
    if any(entry.host == data.host for entry in tenant.domains):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dominio ya agregado")

    if data.is_primary:
        for entry in tenant.domains:
            entry.is_primary = False
    entry = DomainEntry(
        host=data.host,
        verification_token=secrets.token_urlsafe(16),
        is_primary=data.is_primary or not tenant.domains,
    )
    tenant.domains.append(entry)
    try:
        await tenant.save()
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ese dominio ya está registrado"
        )
    await write_audit(
        "domain.add",
        actor_id=user.id,
        tenant_id=tenant.id,
        entity_type="tenant",
        entity_id=tenant.id,
        meta={"host": data.host},
        request=request,
    )
    return entry


@router.post("/me/domains/{host}/verify", response_model=DomainOut)
async def verify_domain(
    host: str,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    entry = _find_domain(tenant, host)
    if not entry.verified:
        matches = await run_in_threadpool(_txt_matches, entry.host, entry.verification_token or "")
        if not matches:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se encontró el registro TXT {}.{} con el token esperado".format(
                    DNS_VERIFY_PREFIX, entry.host
                ),
            )
        entry.verified = True
        await tenant.save()
    return entry


@router.delete("/me/domains/{host}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_domain(
    host: str,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    entry = _find_domain(tenant, host)
    tenant.domains = [d for d in tenant.domains if d.host != entry.host]
    if tenant.domains and not any(d.is_primary for d in tenant.domains):
        tenant.domains[0].is_primary = True
    await tenant.save()
    await write_audit(
        "domain.delete",
        actor_id=user.id,
        tenant_id=tenant.id,
        entity_type="tenant",
        entity_id=tenant.id,
        meta={"host": entry.host},
        request=request,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
