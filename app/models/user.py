from datetime import datetime
from typing import List, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, field_validator
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.models.base import TenantDocument
from app.models.enums import UserRole


class AgentProfile(BaseModel):
    license_no: Optional[str] = None
    bio: Optional[str] = None
    public: bool = True


class User(TenantDocument):
    """Agente o staff de una agencia. El email es único POR tenant."""

    email: str
    password_hash: str
    full_name: str
    phone: Optional[str] = None
    avatar_media_id: Optional[PydanticObjectId] = None
    role: UserRole = UserRole.AGENT
    permissions: List[str] = Field(default_factory=list)
    agent_profile: AgentProfile = Field(default_factory=AgentProfile)
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
        name = "users"
        indexes = [
            IndexModel(
                [("tenant_id", ASCENDING), ("email", ASCENDING)],
                unique=True,
                name="uq_user_tenant_email",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("role", ASCENDING)],
                name="ix_user_tenant_role",
            ),
        ]
