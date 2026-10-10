from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from beanie import Document, PydanticObjectId, Replace, Save, SaveChanges, before_event
from pydantic import Field

# Money: Decimal almacenado como Decimal128 en MongoDB (nunca float).
try:
    from beanie.odm.custom_types.decimal import DecimalAnnotation as Money
except ImportError:  # pragma: no cover
    from decimal import Decimal as Money  # type: ignore

ZERO = Decimal("0")
MAX_VIDEO_SECONDS = 15


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """MongoDB puede devolver datetimes naive; los normalizamos a UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def period_of(dt: datetime) -> str:
    """Devuelve el periodo fiscal 'YYYY-MM' de una fecha."""
    return ensure_utc(dt).strftime("%Y-%m")


def ensure_non_negative(value):
    if value is not None and value < 0:
        raise ValueError("El valor no puede ser negativo")
    return value


class BaseDocument(Document):
    """Documento base con marcas de tiempo. No se registra en init_beanie."""

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @before_event(Replace, Save, SaveChanges)
    def _touch_updated_at(self):
        self.updated_at = utcnow()


class TenantDocument(BaseDocument):
    """Documento base de toda colección de negocio: SIEMPRE lleva tenant_id."""

    tenant_id: PydanticObjectId
