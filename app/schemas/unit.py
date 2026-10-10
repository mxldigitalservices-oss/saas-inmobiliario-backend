from typing import List, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.base import Money, ensure_non_negative
from app.models.enums import Lifecycle, UnitAvailability
from app.schemas.common import TimestampedOut


class UnitCreate(BaseModel):
    """El property_id llega por la ruta (/properties/{id}/units)."""

    code: str = Field(min_length=1, max_length=30)
    label: Optional[str] = Field(None, max_length=120)
    floor: Optional[int] = None
    tower: Optional[str] = Field(None, max_length=30)
    price: Money
    currency: str = Field("USD", min_length=3, max_length=3)
    bedrooms: Optional[int] = Field(None, ge=0)
    bathrooms: Optional[float] = Field(None, ge=0)
    area_m2: Optional[float] = Field(None, gt=0)
    parking: Optional[int] = Field(None, ge=0)
    lifecycle: Lifecycle = Lifecycle.EN_PLANO
    availability: UnitAvailability = UnitAvailability.AVAILABLE
    floor_plan_media_id: Optional[PydanticObjectId] = None
    media_ids: List[PydanticObjectId] = Field(default_factory=list)

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("price")
    @classmethod
    def _price(cls, v):
        return ensure_non_negative(v)


class UnitBulkCreate(BaseModel):
    units: List[UnitCreate] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _unique_codes(self):
        codes = [u.code for u in self.units]
        if len(codes) != len(set(codes)):
            raise ValueError("Hay códigos de unidad repetidos en la carga")
        return self


class UnitUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=30)
    label: Optional[str] = Field(None, max_length=120)
    floor: Optional[int] = None
    tower: Optional[str] = Field(None, max_length=30)
    price: Optional[Money] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    bedrooms: Optional[int] = Field(None, ge=0)
    bathrooms: Optional[float] = Field(None, ge=0)
    area_m2: Optional[float] = Field(None, gt=0)
    parking: Optional[int] = Field(None, ge=0)
    lifecycle: Optional[Lifecycle] = None
    floor_plan_media_id: Optional[PydanticObjectId] = None
    media_ids: Optional[List[PydanticObjectId]] = None

    @field_validator("code")
    @classmethod
    def _code(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().upper() if v is not None else v

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().upper() if v is not None else v

    @field_validator("price")
    @classmethod
    def _price(cls, v):
        return ensure_non_negative(v)


class UnitStatusUpdate(BaseModel):
    availability: Optional[UnitAvailability] = None
    lifecycle: Optional[Lifecycle] = None

    @model_validator(mode="after")
    def _at_least_one(self):
        if self.availability is None and self.lifecycle is None:
            raise ValueError("Debe enviar availability o lifecycle")
        return self


class UnitOut(TimestampedOut):
    tenant_id: PydanticObjectId
    property_id: PydanticObjectId
    code: str
    label: Optional[str] = None
    floor: Optional[int] = None
    tower: Optional[str] = None
    price: Money
    currency: str
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    area_m2: Optional[float] = None
    parking: Optional[int] = None
    lifecycle: Lifecycle
    availability: UnitAvailability
    floor_plan_media_id: Optional[PydanticObjectId] = None
    media_ids: List[PydanticObjectId] = Field(default_factory=list)
    reserved_by_request_id: Optional[PydanticObjectId] = None


class UnitFilter(BaseModel):
    availability: Optional[UnitAvailability] = None
    lifecycle: Optional[Lifecycle] = None
    tower: Optional[str] = None
    floor: Optional[int] = None
    min_price: Optional[Money] = None
    max_price: Optional[Money] = None
    min_bedrooms: Optional[int] = Field(None, ge=0)
