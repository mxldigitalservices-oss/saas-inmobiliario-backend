import re
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, IndexModel

from app.models.base import BaseDocument, Money, ensure_utc, utcnow
from app.models.enums import PlanType, SubscriptionStatus

SLUG_REGEX = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$")


class DomainEntry(BaseModel):
    host: str
    verified: bool = False
    verification_token: Optional[str] = None
    is_primary: bool = False
    added_at: datetime = Field(default_factory=utcnow)

    @field_validator("host")
    @classmethod
    def normalize_host(cls, v: str) -> str:
        v = v.strip().lower()
        for prefix in ("https://", "http://"):
            if v.startswith(prefix):
                v = v[len(prefix):]
        v = v.split("/")[0].split(":")[0]
        if not v or "." not in v:
            raise ValueError("Dominio inválido")
        return v


class Contact(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    whatsapp: Optional[str] = None


class Branding(BaseModel):
    logo_media_id: Optional[PydanticObjectId] = None
    primary_color: str = "#0A5FFF"
    tagline: Optional[str] = None
    contact: Contact = Field(default_factory=Contact)


class TenantFiscal(BaseModel):
    business_name: Optional[str] = None
    rnc: Optional[str] = None
    address: Optional[str] = None
    itbis_default_rate: Money = Decimal("0.18")


class Subscription(BaseModel):
    status: SubscriptionStatus = SubscriptionStatus.TRIAL
    plan: Optional[PlanType] = None
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    active_license_id: Optional[PydanticObjectId] = None


class TenantLimits(BaseModel):
    max_users: int = 3
    max_properties: int = 100
    max_media_mb: int = 2048


class TenantPreferences(BaseModel):
    timezone: str = "America/Santo_Domingo"
    currency: str = "DOP"
    locale: str = "es-DO"


class Tenant(BaseDocument):
    """Agencia / oficina digital. Raíz del aislamiento multi-tenant."""

    slug: str
    name: str
    owner_user_id: Optional[PydanticObjectId] = None
    domains: List[DomainEntry] = Field(default_factory=list)
    branding: Branding = Field(default_factory=Branding)
    fiscal: TenantFiscal = Field(default_factory=TenantFiscal)
    subscription: Subscription = Field(default_factory=Subscription)
    limits: TenantLimits = Field(default_factory=TenantLimits)
    settings: TenantPreferences = Field(default_factory=TenantPreferences)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        v = v.strip().lower()
        if not SLUG_REGEX.match(v):
            raise ValueError(
                "Slug inválido: use minúsculas, números y guiones (3-63 caracteres)"
            )
        return v

    def is_read_only(self, now: Optional[datetime] = None) -> bool:
        """True si el tenant debe operar en modo Solo Lectura."""
        now = ensure_utc(now) or utcnow()
        sub = self.subscription
        if sub.status in (SubscriptionStatus.EXPIRED, SubscriptionStatus.SUSPENDED):
            return True
        expires = ensure_utc(sub.expires_at)
        if expires is not None and expires < now:
            return True
        return False

    @classmethod
    async def find_by_host(
        cls, host: str, base_domain: Optional[str] = None
    ) -> Optional["Tenant"]:
        """Resuelve el tenant desde el Host header.

        1) Dominio personalizado (domains.host).
        2) Subdominio por defecto: {slug}.{base_domain}.
        """
        host = host.strip().lower().split(":")[0]
        tenant = await cls.find_one({"domains.host": host})
        if tenant:
            return tenant
        if base_domain:
            base_domain = base_domain.strip().lower()
            suffix = "." + base_domain
            if host.endswith(suffix):
                slug = host[: -len(suffix)]
                if slug and "." not in slug:
                    return await cls.find_one({"slug": slug})
        return None

    class Settings:
        name = "tenants"
        indexes = [
            IndexModel([("slug", ASCENDING)], unique=True, name="uq_tenant_slug"),
            IndexModel(
                [("domains.host", ASCENDING)],
                unique=True,
                name="uq_tenant_domain_host",
                partialFilterExpression={"domains.host": {"$type": "string"}},
            ),
            IndexModel(
                [("subscription.status", ASCENDING), ("subscription.expires_at", ASCENDING)],
                name="ix_tenant_subscription",
            ),
        ]
