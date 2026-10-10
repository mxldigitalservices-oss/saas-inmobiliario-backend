import math
import re
import unicodedata
from datetime import datetime
from typing import Generic, List, TypeVar

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

PERIOD_REGEX = r"^\d{4}-(0[1-9]|1[0-2])$"
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class APIModel(BaseModel):
    """Base de los schemas de salida: permite construirlos desde documentos Beanie."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class IdOut(APIModel):
    id: PydanticObjectId


class TimestampedOut(IdOut):
    created_at: datetime
    updated_at: datetime


class MessageResponse(APIModel):
    message: str
    success: bool = True


class PageParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size


class Page(APIModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: List[T], total: int, params: PageParams) -> "Page[T]":
        pages = max(math.ceil(total / params.page_size), 1)
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            pages=pages,
        )


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_REGEX.match(value):
        raise ValueError("Email inválido")
    return value


def validate_password_strength(value: str) -> str:
    if len(value) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres")
    if len(value) > 128:
        raise ValueError("La contraseña es demasiado larga")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("La contraseña debe incluir letras y números")
    return value


def slugify(text: str) -> str:
    """Convierte un texto en slug URL-safe (sin acentos, minúsculas, guiones)."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "item"
