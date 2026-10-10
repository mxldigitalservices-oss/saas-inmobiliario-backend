from typing import List, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.base import Money
from app.models.enums import (
    Lifecycle,
    OperationType,
    PropertyKind,
    PropertyType,
    PublishStatus,
)
from app.models.property import (
    SEO,
    Location,
    ProjectDetails,
    SingleDetails,
)
from app.schemas.common import SLUG_PATTERN, APIModel, TimestampedOut


class PropertyCreate(BaseModel):
    kind: PropertyKind = PropertyKind.SINGLE
    title: str = Field(min_length=3, max_length=160)
    slug: Optional[str] = Field(None, max_length=120)  # si falta, se genera del título
    description: Optional[str] = Field(None, max_length=10000)
    operation: OperationType = OperationType.SALE
    type: PropertyType = PropertyType.APARTMENT
    status: PublishStatus = PublishStatus.DRAFT
    lifecycle: Lifecycle = Lifecycle.LISTO
    location: Location = Field(default_factory=Location)
    single: Optional[SingleDetails] = None
    project: Optional[ProjectDetails] = None
    features: List[str] = Field(default_factory=list)
    cover_media_id: Optional[PydanticObjectId] = None
    media_ids: List[PydanticObjectId] = Field(default_factory=list)
    agent_id: Optional[PydanticObjectId] = None
    seo: SEO = Field(default_factory=SEO)

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if not SLUG_PATTERN.match(v):
            raise ValueError("Slug inválido: use minúsculas, números y guiones")
        return v


class PropertyUpdate(BaseModel):
    """Actualización parcial. El 'kind' no se puede cambiar una vez creada."""

    title: Optional[str] = Field(None, min_length=3, max_length=160)
    slug: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = Field(None, max_length=10000)
    operation: Optional[OperationType] = None
    type: Optional[PropertyType] = None
    status: Optional[PublishStatus] = None
    lifecycle: Optional[Lifecycle] = None
    location: Optional[Location] = None
    single: Optional[SingleDetails] = None
    project: Optional[ProjectDetails] = None
    features: Optional[List[str]] = None
    cover_media_id: Optional[PydanticObjectId] = None
    media_ids: Optional[List[PydanticObjectId]] = None
    agent_id: Optional[PydanticObjectId] = None
    seo: Optional[SEO] = None

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if not SLUG_PATTERN.match(v):
            raise ValueError("Slug inválido: use minúsculas, números y guiones")
        return v


class PropertyOut(TimestampedOut):
    tenant_id: PydanticObjectId
    kind: PropertyKind
    title: str
    slug: str
    description: Optional[str] = None
    operation: OperationType
    type: PropertyType
    status: PublishStatus
    lifecycle: Lifecycle
    location: Location
    single: Optional[SingleDetails] = None
    project: Optional[ProjectDetails] = None
    features: List[str] = Field(default_factory=list)
    cover_media_id: Optional[PydanticObjectId] = None
    media_ids: List[PydanticObjectId] = Field(default_factory=list)
    agent_id: Optional[PydanticObjectId] = None
    seo: SEO


class PropertyListItem(APIModel):
    """Versión liviana para listados y tarjetas del catálogo."""

    id: PydanticObjectId
    kind: PropertyKind
    title: str
    slug: str
    operation: OperationType
    type: PropertyType
    status: PublishStatus
    lifecycle: Lifecycle
    location: Location
    single: Optional[SingleDetails] = None
    project: Optional[ProjectDetails] = None
    cover_media_id: Optional[PydanticObjectId] = None


class PropertyFilter(BaseModel):
    q: Optional[str] = Field(None, max_length=120)
    kind: Optional[PropertyKind] = None
    operation: Optional[OperationType] = None
    type: Optional[PropertyType] = None
    status: Optional[PublishStatus] = None
    lifecycle: Optional[Lifecycle] = None
    city: Optional[str] = None
    sector: Optional[str] = None
    min_price: Optional[Money] = None
    max_price: Optional[Money] = None
    min_bedrooms: Optional[int] = Field(None, ge=0)
    agent_id: Optional[PydanticObjectId] = None
    near_lng: Optional[float] = Field(None, ge=-180, le=180)
    near_lat: Optional[float] = Field(None, ge=-90, le=90)
    radius_km: Optional[float] = Field(None, gt=0, le=500)

    @model_validator(mode="after")
    def _geo_complete(self):
        geo = [self.near_lng, self.near_lat, self.radius_km]
        provided = [g is not None for g in geo]
        if any(provided) and not all(provided):
            raise ValueError("near_lng, near_lat y radius_km deben enviarse juntos")
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("min_price no puede ser mayor que max_price")
        return self
