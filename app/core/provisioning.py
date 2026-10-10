from datetime import timedelta
from typing import Optional, Tuple

from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core import security
from app.models.base import utcnow
from app.models.enums import PlanType, SubscriptionStatus, UserRole
from app.models.tenant import Subscription, Tenant, TenantFiscal, TenantLimits
from app.models.user import User

RESERVED_SLUGS = {
    "www", "api", "admin", "app", "mail", "static", "assets", "cdn", "docs",
    "login", "register", "dashboard", "panel", "support", "help", "staging", "dev",
}


async def provision_tenant(
    *,
    slug: str,
    name: str,
    owner_email: str,
    owner_full_name: str,
    password: str,
    plan: PlanType = PlanType.TRIAL_30D,
    duration_days: int = 30,
    limits: Optional[TenantLimits] = None,
    phone: Optional[str] = None,
) -> Tuple[Tenant, User]:
    """Crea una agencia con su usuario propietario y su suscripción inicial."""
    if slug in RESERVED_SLUGS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Ese subdominio está reservado"
        )

    now = utcnow()
    tenant = Tenant(
        slug=slug,
        name=name,
        fiscal=TenantFiscal(business_name=name),
        subscription=Subscription(
            status=(
                SubscriptionStatus.TRIAL
                if plan == PlanType.TRIAL_30D
                else SubscriptionStatus.ACTIVE
            ),
            plan=plan,
            starts_at=now,
            expires_at=now + timedelta(days=duration_days),
        ),
        limits=limits or TenantLimits(),
    )
    try:
        await tenant.insert()
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="El subdominio ya está en uso"
        )

    user = User(
        tenant_id=tenant.id,
        email=owner_email,
        password_hash=security.hash_password(password),
        full_name=owner_full_name,
        phone=phone,
        role=UserRole.OWNER,
    )
    try:
        await user.insert()
    except Exception:
        await tenant.delete()
        raise

    tenant.owner_user_id = user.id
    await tenant.save()
    return tenant, user
