from datetime import datetime
from typing import List, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import LicenseStatus, PlanType
from app.models.tenant import Subscription
from app.models.token import LicensePeriod, LimitsOverride
from app.schemas.common import APIModel, TimestampedOut


class LicenseCreate(BaseModel):
    """El Super Admin genera uno o varios tokens de activación."""

    plan: PlanType = PlanType.TRIAL_30D
    duration_days: Optional[int] = Field(None, ge=1, le=3650)
    quantity: int = Field(1, ge=1, le=100)
    valid_until_redeem: Optional[datetime] = None
    limits_override: LimitsOverride = Field(default_factory=LimitsOverride)
    payment_ref: Optional[str] = Field(None, max_length=120)
    notes: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def _default_duration(self):
        if self.duration_days is None:
            if self.plan == PlanType.TRIAL_30D:
                self.duration_days = 30
            elif self.plan == PlanType.ANNUAL:
                self.duration_days = 365
            else:
                raise ValueError("duration_days es obligatorio para el plan custom")
        return self


class LicenseOut(TimestampedOut):
    """Nunca expone token_hash."""

    token_prefix: str
    plan: PlanType
    duration_days: int
    limits_override: LimitsOverride
    status: LicenseStatus
    created_by: PydanticObjectId
    valid_until_redeem: Optional[datetime] = None
    redeemed_by_tenant_id: Optional[PydanticObjectId] = None
    redeemed_at: Optional[datetime] = None
    period: LicensePeriod
    payment_ref: Optional[str] = None
    notes: Optional[str] = None


class LicenseCreatedOut(LicenseOut):
    """Respuesta de creación: el token en claro se muestra UNA sola vez."""

    token: str


class LicenseBatchCreatedOut(BaseModel):
    items: List[LicenseCreatedOut]


class LicenseRedeemRequest(BaseModel):
    token: str = Field(min_length=8, max_length=128)

    @field_validator("token")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class LicenseRedeemOut(APIModel):
    message: str = "Licencia activada correctamente"
    subscription: Subscription
    read_only: bool = False


class LicenseRevokeRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=300)
