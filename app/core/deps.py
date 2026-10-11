import json
from typing import Any, Callable, Dict, Optional, Type, TypeVar

from beanie import PydanticObjectId
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from app.core import security
from app.core.config import settings
from app.models.enums import UserRole
from app.models.super_admin import SuperAdmin
from app.models.tenant import SLUG_REGEX, Tenant
from app.models.user import User
from app.schemas.common import PageParams

bearer_scheme = HTTPBearer(auto_error=False)

STAFF_ROLES = (UserRole.OWNER, UserRole.ADMIN, UserRole.AGENT, UserRole.VIEWER)
STAFF_WRITE_ROLES = (UserRole.OWNER, UserRole.ADMIN, UserRole.AGENT)
ADMIN_ROLES = (UserRole.OWNER, UserRole.ADMIN)

M = TypeVar("M")


def to_object_id(value: Any) -> Optional[PydanticObjectId]:
    if not value:
        return None
    try:
        return PydanticObjectId(str(value))
    except Exception:
        return None


def build_model(model_cls: Type[M], **kwargs: Any) -> M:
    """Construye un schema de filtros; los errores de validación se devuelven como 422."""
    try:
        return model_cls(**kwargs)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=json.loads(exc.json()),
        )


def get_page_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


def _unauthorized(detail: str = "No autenticado") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _payload(creds: Optional[HTTPAuthorizationCredentials], audience: str) -> Dict[str, Any]:
    if creds is None or creds.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        return security.decode_token(
            creds.credentials, expected_type="access", expected_audience=audience
        )
    except ValueError as exc:
        raise _unauthorized(str(exc))


# ------------------------------------------------------------------ tenant (Host)
def _request_host(request: Request) -> str:
    host = request.headers.get("host") or request.headers.get("x-forwarded-host") or ""
    return host.split(",")[0].strip().lower().split(":")[0]


async def _tenant_by_host(host: str) -> Optional[Tenant]:
    """Dominio propio verificado o subdominio {slug}.BASE_DOMAIN. None si no hay coincidencia."""
    if not host:
        return None
    tenant = await Tenant.find_one(
        {"domains": {"$elemMatch": {"host": host, "verified": True}}}
    )
    base = settings.BASE_DOMAIN
    if tenant is None and base and host.endswith("." + base):
        slug = host[: -(len(base) + 1)]
        if slug and "." not in slug:
            tenant = await Tenant.find_one({"slug": slug})
    return tenant


def _platform_hosts() -> set:
    """Hosts de la plataforma (login/panel): nunca representan a una agencia concreta."""
    hosts = {"localhost", "127.0.0.1", "0.0.0.0", "testserver"}
    base = settings.BASE_DOMAIN
    if base:
        hosts.update({base, "www." + base})
    if settings.RAILWAY_PUBLIC_DOMAIN:
        hosts.add(settings.RAILWAY_PUBLIC_DOMAIN.strip().lower())
    return hosts


async def tenant_from_host(request: Request) -> Optional[Tenant]:
    """Agencia dueña del dominio de la petición, o None si es el host de la plataforma."""
    host = _request_host(request)
    if not host or host in _platform_hosts():
        return None
    return await _tenant_by_host(host)


async def resolve_tenant(request: Request) -> Tenant:
    """Identifica la agencia por el Host header.

    1) Dominio propio verificado (domains.host).
    2) Subdominio por defecto: {slug}.BASE_DOMAIN.
    3) Solo desarrollo: header X-Tenant-Slug.
    (La caché en Redis de esta resolución se añadirá en un bloque posterior.)
    """
    host = _request_host(request)
    tenant = await _tenant_by_host(host)

    if tenant is None and settings.ALLOW_TENANT_HEADER:
        header_slug = (request.headers.get("x-tenant-slug") or "").strip().lower()
        if header_slug:
            tenant = await Tenant.find_one({"slug": header_slug})

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agencia no encontrada para este dominio"
        )
    return tenant


async def resolve_public_tenant(
    request: Request,
    agency: Optional[str] = Query(
        None,
        max_length=63,
        description="Slug de la agencia. Solo se usa cuando el Host no es de una agencia.",
    ),
) -> Tenant:
    """Agencia del catálogo público (solo lectura).

    Prioridad:
    1) Host: dominio propio verificado o {slug}.BASE_DOMAIN. Si el Host pertenece a una
       agencia, MANDA siempre y se ignora cualquier ?agency= (nunca se mezclan agencias
       en el dominio de otra).
    2) Host de la plataforma: ?agency=<slug> o header X-Tenant-Slug (enlaces compartibles
       tipo /a/<slug>). Esto solo se acepta en endpoints públicos que exponen únicamente
       datos publicados; las rutas autenticadas siguen usando resolve_tenant / el JWT.
    """
    tenant = await _tenant_by_host(_request_host(request))
    if tenant is not None:
        return tenant

    slug = (agency or request.headers.get("x-tenant-slug") or "").strip().lower()
    if slug and SLUG_REGEX.match(slug):
        tenant = await Tenant.find_one({"slug": slug})
        if tenant is not None:
            return tenant

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Agencia no encontrada para este dominio"
    )


# ---------------------------------------------------------------- usuario / tenant
async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> User:
    data = _payload(creds, "tenant")
    user_id = to_object_id(data.get("sub"))
    tenant_id = to_object_id(data.get("tenant_id"))
    if user_id is None or tenant_id is None:
        raise _unauthorized("Token inválido")
    user = await User.get(user_id)
    if user is None or not user.is_active or user.tenant_id != tenant_id:
        raise _unauthorized("Usuario no válido")
    return user


async def get_current_tenant(user: User = Depends(get_current_user)) -> Tenant:
    tenant = await Tenant.get(user.tenant_id)
    if tenant is None:
        raise _unauthorized("Agencia no válida")
    return tenant


def require_roles(*roles: UserRole) -> Callable[..., Any]:
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para esta acción",
            )
        return user

    return checker


async def require_writable_tenant(tenant: Tenant = Depends(get_current_tenant)) -> Tenant:
    """Bloquea acciones de escritura (facturar, contratos) si la licencia venció."""
    if tenant.is_read_only():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "tenant_read_only",
                "message": "La licencia de la agencia venció: modo Solo Lectura",
            },
        )
    return tenant


async def get_current_super_admin(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> SuperAdmin:
    data = _payload(creds, "superadmin")
    admin_id = to_object_id(data.get("sub"))
    if admin_id is None:
        raise _unauthorized("Token inválido")
    admin = await SuperAdmin.get(admin_id)
    if admin is None or not admin.is_active:
        raise _unauthorized("Super Admin no válido")
    return admin
