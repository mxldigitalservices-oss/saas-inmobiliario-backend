from datetime import datetime
from typing import List, Literal, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator, model_validator
from pymongo import ASCENDING, DESCENDING, GEOSPHERE, TEXT, IndexModel

from app.models.base import Money, TenantDocument, ensure_non_negative
from app.models.enums import (
    Lifecycle,
    OperationType,
    PropertyKind,
    PropertyType,
    PublishStatus,
    SingleAvailability,
)


class GeoPoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: List[float]  # [longitud, latitud]

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, v: List[float]) -> List[float]:
        if len(v) != 2:
            raise ValueError("coordinates debe ser [longitud, latitud]")
        lng, lat = v
        if not (-180 <= lng <= 180 and -90 <= lat <= 90):
            raise ValueError("Coordenadas fuera de rango")
        return v


class Location(BaseModel):
    country: str = "DO"
    province: Optional[str] = None
    city: Optional[str] = None
    sector: Optional[str] = None
    address: Optional[str] = None
    geo: Optional[GeoPoint] = None


class SingleDetails(BaseModel):
    """Datos de una propiedad individual (casa, terreno, local...)."""

    price: Optional[Money] = None
    currency: str = "USD"
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    area_m2: Optional[float] = None
    parking: Optional[int] = None
    availability: SingleAvailability = SingleAvailability.AVAILABLE

    @field_validator("price")
    @classmethod
    def price_non_negative(cls, v):
        return ensure_non_negative(v)


class UnitsSummary(BaseModel):
    """Resumen denormalizado, se recalcula al cambiar una unidad."""

    available: int = 0
    reserved: int = 0
    sold: int = 0
    price_min: Optional[Money] = None
    price_max: Optional[Money] = None


class ProjectDetails(BaseModel):
    """Datos de un proyecto / torre que contiene unidades."""

    developer: Optional[str] = None
    delivery_date: Optional[datetime] = None
    total_units: int = 0
    floors: Optional[int] = None
    amenities: List[str] = Field(default_factory=list)
    units_summary: UnitsSummary = Field(default_factory=UnitsSummary)


class SEO(BaseModel):
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None


class Property(TenantDocument):
    """Propiedad individual (kind=single) o proyecto/torre (kind=project)."""

    kind: PropertyKind = PropertyKind.SINGLE
    title: str
    slug: str
    description: Optional[str] = None
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
    def normalize_slug(cls, v: str) -> str:
        return v.strip().lower()

    @model_validator(mode="after")
    def enforce_kind_coherence(self):
        if self.kind == PropertyKind.SINGLE:
            self.project = None
            if self.single is None:
                self.single = SingleDetails()
        else:
            self.single = None
            if self.project is None:
                self.project = ProjectDetails()
        return self

    class Settings:
        name = "properties"
        indexes = [
            IndexModel(
                [("tenant_id", ASCENDING), ("slug", ASCENDING)],
                unique=True,
                name="uq_property_tenant_slug",
            ),
            IndexModel(
                [
                    ("tenant_id", ASCENDING),
                    ("status", ASCENDING),
                    ("kind", ASCENDING),
                    ("created_at", DESCENDING),
                ],
                name="ix_property_tenant_status_kind",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("agent_id", ASCENDING)],
                name="ix_property_tenant_agent",
            ),
            IndexModel([("location.geo", GEOSPHERE)], name="ix_property_geo"),
            IndexModel(
                [("title", TEXT), ("description", TEXT)],
                default_language="spanish",
                name="tx_property_title_description",
            ),
        ]
