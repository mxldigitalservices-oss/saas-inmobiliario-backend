from datetime import datetime
from typing import Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import NCFStatus
from app.schemas.common import TimestampedOut

NCF_TYPE_PATTERN = r"^[BE]\d{2}$"


class NCFSequenceCreate(BaseModel):
    ncf_type: str = Field(pattern=NCF_TYPE_PATTERN)  # B01, B02, B14, B15, E31...
    prefix: Optional[str] = Field(None, max_length=4)  # por defecto = ncf_type
    range_from: int = Field(ge=1)
    range_to: int = Field(ge=1)
    expires_on: Optional[datetime] = None
    authorization_no: Optional[str] = Field(None, max_length=60)

    # mode="before": normaliza (strip + mayúsculas) ANTES de validar el pattern
    @field_validator("ncf_type", "prefix", mode="before")
    @classmethod
    def _upper(cls, v):
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @model_validator(mode="after")
    def _range(self):
        if self.range_to < self.range_from:
            raise ValueError("range_to debe ser mayor o igual a range_from")
        if not self.prefix:
            self.prefix = self.ncf_type
        return self


class NCFSequenceUpdate(BaseModel):
    status: Optional[NCFStatus] = None
    expires_on: Optional[datetime] = None
    authorization_no: Optional[str] = Field(None, max_length=60)


class NCFSequenceOut(TimestampedOut):
    tenant_id: PydanticObjectId
    ncf_type: str
    prefix: str
    range_from: int
    range_to: int
    current: int
    remaining: int
    expires_on: Optional[datetime] = None
    status: NCFStatus
    authorization_no: Optional[str] = None
