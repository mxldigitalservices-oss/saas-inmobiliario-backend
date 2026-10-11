from datetime import datetime
from typing import List, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator

from app.models.base import ensure_utc, utcnow
from app.models.enums import PlanType, SubscriptionStatus
from app.models.tenant import (
    SLUG_REGEX,
    Branding,
    DomainEntry,
    Subscription,
    TenantFiscal,
    TenantLimits,
    TenantPreferences,
)
from app.schemas.common import (
    APIModel,
    TimestampedOut,
    normalize_email,
    validate_password_strength,
)


class TenantCreate(BaseModel):
    """Creación de una agencia por el Super Admin."""

    slug: str = Field(min_length=3, max_length=63)
    name: str = Field(min_length=2, max_length=120)
    owner_email: str
    owner_full_name: str = Field(min_length=2, max_length=120)
    owner_password: str
    plan: PlanType = PlanType.TRIAL_30D
    duration_days: int = Field(30, ge=1, le=3650)
    limits: Optional[TenantLimits] = None

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        v = v.strip().lower()
        if not SLUG_REGEX.match(v):
            raise ValueError("Slug inválido: use minúsculas, números y guiones")
        return v

    @field_validator("owner_email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)

    @field_validator("owner_password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validate_password_strength(v)


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    branding: Optional[Branding] = None
    fiscal: Optional[TenantFiscal] = None
    settings: Optional[TenantPreferences] = None


class DomainAddRequest(BaseModel):
    host: str = Field(min_length=4, max_length=253)
    is_primary: bool = False

    @field_validator("host")
    @classmethod
    def _host(cls, v: str) -> str:
        # Reutiliza la normalización/validación del modelo DomainEntry
        return DomainEntry(host=v).host


class DomainOut(APIModel):
    host: str
    verified: bool
    is_primary: bool
    verification_token: Optional[str] = None
    added_at: datetime


class SubscriptionAdminUpdate(BaseModel):
    """Ajuste manual de la suscripción por el Super Admin."""

    status: Optional[SubscriptionStatus] = None
    plan: Optional[PlanType] = None
    expires_at: Optional[datetime] = None
    extend_days: Optional[int] = Field(None, ge=1, le=3650)
    limits: Optional[TenantLimits] = None


class SubscriptionStatusOut(BaseModel):
    """Estado de la licencia, para el banner de 'Solo Lectura' del frontend."""

    status: SubscriptionStatus
    plan: Optional[PlanType] = None
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    read_only: bool = False
    days_remaining: Optional[int] = None

    @classmethod
    def from_tenant(cls, tenant, now: Optional[datetime] = None) -> "SubscriptionStatusOut":
        now = ensure_utc(now) or utcnow()
        sub = tenant.subscription
        expires = ensure_utc(sub.expires_at)
        days = None
        if expires is not None:
            days = max((expires - now).days, 0)
        return cls(
            status=sub.status,
            plan=sub.plan,
            starts_at=sub.starts_at,
            expires_at=sub.expires_at,
            read_only=tenant.is_read_only(now),
            days_remaining=days,
        )


class TenantOut(TimestampedOut):
    slug: str
    name: str
    owner_user_id: Optional[PydanticObjectId] = None
    domains: List[DomainOut] = Field(default_factory=list)
    branding: Branding
    fiscal: TenantFiscal
    subscription: Subscription
    limits: TenantLimits
    settings: TenantPreferences
    read_only: bool = False

    @classmethod
    def from_tenant(cls, tenant) -> "TenantOut":
        out = cls.model_validate(tenant)
        out.read_only = tenant.is_read_only()
        return out


class TenantListItem(APIModel):
    id: PydanticObjectId
    slug: str
    name: str
    subscription: Subscription
    created_at: datetime


class TenantPublicOut(APIModel):
    """Datos públicos de la agencia que se sirven según el Host header."""

    slug: str
    name: str
    branding: Branding
    settings: TenantPreferences
    logo_url: Optional[str] = None
