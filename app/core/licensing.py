from datetime import timedelta

from fastapi import HTTPException, status
from pymongo import ReturnDocument

from app.core import security
from app.core.db_utils import raw_collection
from app.models.base import ensure_utc, utcnow
from app.models.enums import LicenseStatus, PlanType, SubscriptionStatus
from app.models.tenant import Tenant
from app.models.token import LicensePeriod, LicenseToken


async def redeem_license(tenant: Tenant, raw_token: str) -> Tenant:
    """Canje ATÓMICO de un token de activación y actualización de la suscripción."""
    now = utcnow()
    token_hash = security.hash_license_token(raw_token)
    collection = raw_collection(LicenseToken)
    doc = await collection.find_one_and_update(
        {
            "token_hash": token_hash,
            "status": LicenseStatus.UNUSED.value,
            "$or": [
                {"valid_until_redeem": None},
                {"valid_until_redeem": {"$gte": now}},
            ],
        },
        {
            "$set": {
                "status": LicenseStatus.REDEEMED.value,
                "redeemed_by_tenant_id": tenant.id,
                "redeemed_at": now,
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token inválido, ya utilizado o vencido",
        )

    license_doc = await LicenseToken.get(doc["_id"])
    if license_doc is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="No se pudo cargar la licencia")

    sub = tenant.subscription
    current_expiry = ensure_utc(sub.expires_at)
    still_active = current_expiry is not None and current_expiry > now

    # Un plan pagado reemplaza el periodo de prueba; una renovación se suma al vigente.
    if still_active and not (
        sub.status == SubscriptionStatus.TRIAL and license_doc.plan != PlanType.TRIAL_30D
    ):
        start = current_expiry
    else:
        start = now
    ends = start + timedelta(days=license_doc.duration_days)

    license_doc.period = LicensePeriod(starts_at=start, ends_at=ends)
    await license_doc.save()

    sub.status = (
        SubscriptionStatus.TRIAL
        if license_doc.plan == PlanType.TRIAL_30D
        else SubscriptionStatus.ACTIVE
    )
    sub.plan = license_doc.plan
    if not still_active or start == now:
        sub.starts_at = start
    sub.expires_at = ends
    sub.active_license_id = license_doc.id

    override = license_doc.limits_override
    for name in ("max_users", "max_properties", "max_media_mb"):
        value = getattr(override, name)
        if value is not None:
            setattr(tenant.limits, name, value)

    await tenant.save()
    return tenant
