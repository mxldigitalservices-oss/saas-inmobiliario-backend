from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core import security
from app.core.audit import write_audit
from app.core.config import settings
from app.core.deps import (
    _unauthorized,
    get_current_tenant,
    get_current_user,
    resolve_tenant,
    to_object_id,
)
from app.core.licensing import redeem_license
from app.core.provisioning import provision_tenant
from app.models.base import utcnow
from app.models.enums import AuditActorType, PlanType
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentUserOut,
    LoginRequest,
    RefreshTokenRequest,
    RegisterTenantRequest,
    SuperAdminLoginRequest,
    TokenResponse,
)
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _role_value(user: User) -> str:
    return getattr(user.role, "value", user.role)


def _token_response(user: User) -> TokenResponse:
    access = security.create_token(
        subject=str(user.id),
        audience="tenant",
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
        tenant_id=str(user.tenant_id),
        role=_role_value(user),
    )
    refresh = security.create_token(
        subject=str(user.id),
        audience="tenant",
        token_type="refresh",
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_DAYS),
        tenant_id=str(user.tenant_id),
        role=_role_value(user),
    )
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_MINUTES * 60,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterTenantRequest, request: Request):
    """Registro self-service: crea la agencia (prueba de 30 días) y su propietario."""
    tenant, user = await provision_tenant(
        slug=data.slug,
        name=data.agency_name,
        owner_email=data.owner_email,
        owner_full_name=data.owner_full_name,
        password=data.password,
        plan=PlanType.TRIAL_30D,
        duration_days=30,
        phone=data.phone,
    )
    if data.activation_token:
        try:
            tenant = await redeem_license(tenant, data.activation_token)
        except HTTPException:
            await user.delete()
            await tenant.delete()
            raise
    await write_audit(
        "tenant.register",
        actor_id=user.id,
        tenant_id=tenant.id,
        entity_type="tenant",
        entity_id=tenant.id,
        request=request,
    )
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    tenant: Tenant = Depends(resolve_tenant),
):
    """Login de un agente. La agencia se identifica por el Host header."""
    user = await User.find_one({"tenant_id": tenant.id, "email": data.email})
    stored_hash = user.password_hash if user is not None else security.dummy_hash()
    valid = security.verify_password(data.password, stored_hash)
    if user is None or not valid or not user.is_active:
        raise _unauthorized("Credenciales inválidas")
    user.last_login_at = utcnow()
    await user.save()
    return _token_response(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshTokenRequest):
    try:
        payload = security.decode_token(
            data.refresh_token, expected_type="refresh", expected_audience="tenant"
        )
    except ValueError as exc:
        raise _unauthorized(str(exc))
    user_id = to_object_id(payload.get("sub"))
    tenant_id = to_object_id(payload.get("tenant_id"))
    user = await User.get(user_id) if user_id else None
    if user is None or not user.is_active or user.tenant_id != tenant_id:
        raise _unauthorized("Usuario no válido")
    return _token_response(user)


@router.get("/me", response_model=CurrentUserOut)
async def me(
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    out = CurrentUserOut.model_validate(user)
    out.tenant_read_only = tenant.is_read_only()
    return out


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    data: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    if not security.verify_password(data.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña actual es incorrecta"
        )
    user.password_hash = security.hash_password(data.new_password)
    await user.save()
    await write_audit(
        "user.change_password",
        actor_id=user.id,
        tenant_id=user.tenant_id,
        entity_type="user",
        entity_id=user.id,
        request=request,
    )
    return MessageResponse(message="Contraseña actualizada")


@router.post("/superadmin/login", response_model=TokenResponse)
async def superadmin_login(data: SuperAdminLoginRequest, request: Request):
    admin = await SuperAdmin.find_one({"email": data.email})
    stored_hash = admin.password_hash if admin is not None else security.dummy_hash()
    valid = security.verify_password(data.password, stored_hash)
    if admin is None or not valid or not admin.is_active:
        raise _unauthorized("Credenciales inválidas")
    admin.last_login_at = utcnow()
    await admin.save()
    access = security.create_token(
        subject=str(admin.id),
        audience="superadmin",
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
    )
    await write_audit(
        "superadmin.login",
        actor_type=AuditActorType.SUPER_ADMIN,
        actor_id=admin.id,
        request=request,
    )
    return TokenResponse(access_token=access, expires_in=settings.ACCESS_TOKEN_MINUTES * 60)
