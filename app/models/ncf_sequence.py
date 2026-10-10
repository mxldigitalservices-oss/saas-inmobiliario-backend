from datetime import datetime
from typing import Optional

from pydantic import model_validator
from pymongo import ASCENDING, IndexModel

from app.models.base import TenantDocument
from app.models.enums import NCFStatus


class NCFSequence(TenantDocument):
    """Secuencia fiscal autorizada por la DGII.

    La asignación del siguiente número debe hacerse de forma ATÓMICA:
    find_one_and_update({tenant_id, ncf_type, status:'active',
    $expr:{$lt:['$current','$range_to']}}, {$inc:{current:1}}).
    """

    ncf_type: str  # B01, B02, B14, B15, ... (configurable, no enum fijo)
    prefix: str
    range_from: int
    range_to: int
    current: int = 0  # último número usado
    expires_on: Optional[datetime] = None
    status: NCFStatus = NCFStatus.ACTIVE
    authorization_no: Optional[str] = None

    @model_validator(mode="after")
    def validate_range(self):
        if self.range_to < self.range_from:
            raise ValueError("range_to debe ser mayor o igual a range_from")
        if self.current < self.range_from - 1:
            self.current = self.range_from - 1
        return self

    @property
    def remaining(self) -> int:
        return max(self.range_to - self.current, 0)

    def format_ncf(self, number: int) -> str:
        """Formato clásico de 11 caracteres: B01 + 8 dígitos."""
        return f"{self.prefix}{number:08d}"

    class Settings:
        name = "ncf_sequences"
        indexes = [
            IndexModel(
                [("tenant_id", ASCENDING), ("ncf_type", ASCENDING), ("status", ASCENDING)],
                name="ix_ncf_tenant_type_status",
            ),
            IndexModel(
                [
                    ("tenant_id", ASCENDING),
                    ("ncf_type", ASCENDING),
                    ("prefix", ASCENDING),
                    ("range_from", ASCENDING),
                ],
                unique=True,
                name="uq_ncf_tenant_range",
            ),
        ]
