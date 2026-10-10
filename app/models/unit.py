from typing import List, Optional

from beanie import PydanticObjectId
from pydantic import Field, field_validator
from pymongo import ASCENDING, IndexModel

from app.models.base import Money, TenantDocument, ensure_non_negative
from app.models.enums import Lifecycle, UnitAvailability


class Unit(TenantDocument):
    """Unidad individual dentro de un proyecto (ej. Apartamento 1A)."""

    property_id: PydanticObjectId
    code: str
    label: Optional[str] = None
    floor: Optional[int] = None
    tower: Optional[str] = None
    price: Money
    currency: str = "USD"
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    area_m2: Optional[float] = None
    parking: Optional[int] = None
    lifecycle: Lifecycle = Lifecycle.EN_PLANO
    availability: UnitAvailability = UnitAvailability.AVAILABLE
    floor_plan_media_id: Optional[PydanticObjectId] = None
    media_ids: List[PydanticObjectId] = Field(default_factory=list)
    reserved_by_request_id: Optional[PydanticObjectId] = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("price")
    @classmethod
    def price_non_negative(cls, v):
        return ensure_non_negative(v)

    class Settings:
        name = "units"
        indexes = [
            IndexModel(
                [("tenant_id", ASCENDING), ("property_id", ASCENDING), ("code", ASCENDING)],
                unique=True,
                name="uq_unit_tenant_property_code",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("property_id", ASCENDING), ("availability", ASCENDING)],
                name="ix_unit_property_availability",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("lifecycle", ASCENDING), ("price", ASCENDING)],
                name="ix_unit_lifecycle_price",
            ),
        ]
