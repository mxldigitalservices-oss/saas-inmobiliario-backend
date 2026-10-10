import json
from typing import Any, Dict, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator

from app.models.enums import GatewayEnvironment, PaymentProvider
from app.schemas.common import TimestampedOut


def _validate_credentials(value: Dict[str, Any]) -> Dict[str, Any]:
    if not value:
        raise ValueError("Las credenciales no pueden estar vacías")
    if any(not isinstance(k, str) or not k.strip() for k in value.keys()):
        raise ValueError("Las claves de las credenciales deben ser texto no vacío")
    if len(json.dumps(value, default=str)) > 10000:
        raise ValueError("Las credenciales exceden el tamaño permitido")
    return value


class GatewayCreate(BaseModel):
    """Las credenciales llegan en claro por HTTPS y se cifran antes de guardarse."""

    provider: PaymentProvider
    label: Optional[str] = Field(None, max_length=80)
    environment: GatewayEnvironment = GatewayEnvironment.SANDBOX
    credentials: Dict[str, Any]
    is_active: bool = True

    @field_validator("credentials")
    @classmethod
    def _credentials(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        return _validate_credentials(v)


class GatewayUpdate(BaseModel):
    label: Optional[str] = Field(None, max_length=80)
    credentials: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

    @field_validator("credentials")
    @classmethod
    def _credentials(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return _validate_credentials(v) if v is not None else v


class GatewayOut(TimestampedOut):
    """Nunca expone credentials_enc; solo pistas no sensibles (public_hint)."""

    tenant_id: PydanticObjectId
    provider: PaymentProvider
    label: Optional[str] = None
    environment: GatewayEnvironment
    public_hint: Dict[str, str] = Field(default_factory=dict)
    is_active: bool
    created_by: Optional[PydanticObjectId] = None
