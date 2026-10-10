from typing import Dict, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel

from app.models.base import TenantDocument
from app.models.enums import GatewayEnvironment, PaymentProvider


class EncryptedPayload(BaseModel):
    """JSON de credenciales cifrado (AES-256-GCM). Todo en base64."""

    ciphertext_b64: str
    iv_b64: str
    auth_tag_b64: str
    alg: str = "AES-256-GCM"
    key_version: int = 1


class PaymentGateway(TenantDocument):
    """Credenciales de pasarela de pago de un agente (Stripe, Azul, CardNET).

    La API NUNCA debe devolver credentials_enc; solo public_hint.
    """

    provider: PaymentProvider
    label: Optional[str] = None
    environment: GatewayEnvironment = GatewayEnvironment.SANDBOX
    credentials_enc: EncryptedPayload
    public_hint: Dict[str, str] = Field(default_factory=dict)
    is_active: bool = True
    created_by: Optional[PydanticObjectId] = None

    class Settings:
        name = "payment_gateways"
        indexes = [
            IndexModel(
                [("tenant_id", ASCENDING), ("provider", ASCENDING), ("environment", ASCENDING)],
                unique=True,
                name="uq_gateway_tenant_provider_env",
            ),
        ]
