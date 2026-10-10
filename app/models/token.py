from datetime import datetime
from typing import Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.base import BaseDocument, ensure_utc, utcnow
from app.models.enums import LicenseStatus, PlanType


class LimitsOverride(BaseModel):
    max_users: Optional[int] = None
    max_properties: Optional[int] = None
    max_media_mb: Optional[int] = None


class LicensePeriod(BaseModel):
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class LicenseToken(BaseDocument):
    """Token de activación generado por el Super Admin.

    El token en claro se muestra UNA sola vez al crearlo; aquí solo se guarda
    su hash (sha256) y un prefijo para identificarlo.
    """

    token_hash: str
    token_prefix: str
    plan: PlanType = PlanType.TRIAL_30D
    duration_days: int = 30
    limits_override: LimitsOverride = Field(default_factory=LimitsOverride)
    status: LicenseStatus = LicenseStatus.UNUSED
    created_by: PydanticObjectId
    valid_until_redeem: Optional[datetime] = None
    redeemed_by_tenant_id: Optional[PydanticObjectId] = None
    redeemed_at: Optional[datetime] = None
    period: LicensePeriod = Field(default_factory=LicensePeriod)
    payment_ref: Optional[str] = None
    notes: Optional[str] = None

    def is_redeemable(self, now: Optional[datetime] = None) -> bool:
        now = ensure_utc(now) or utcnow()
        if self.status != LicenseStatus.UNUSED:
            return False
        limit = ensure_utc(self.valid_until_redeem)
        return limit is None or limit >= now

    class Settings:
        name = "license_tokens"
        indexes = [
            IndexModel([("token_hash", ASCENDING)], unique=True, name="uq_license_token_hash"),
            IndexModel([("status", ASCENDING)], name="ix_license_status"),
            IndexModel(
                [("redeemed_by_tenant_id", ASCENDING), ("period.ends_at", DESCENDING)],
                name="ix_license_tenant_period",
            ),
        ]
