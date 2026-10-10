from datetime import datetime
from typing import Optional

from pydantic import field_validator
from pymongo import ASCENDING, IndexModel

from app.models.base import BaseDocument


class SuperAdmin(BaseDocument):
    """Dueño del SaaS. Colección SIN tenant_id, con autenticación separada."""

    email: str
    password_hash: str
    full_name: Optional[str] = None
    mfa_secret_enc: Optional[str] = None
    is_active: bool = True
    last_login_at: Optional[datetime] = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("Email inválido")
        return v

    class Settings:
        name = "super_admins"
        indexes = [
            IndexModel([("email", ASCENDING)], unique=True, name="uq_superadmin_email"),
        ]
