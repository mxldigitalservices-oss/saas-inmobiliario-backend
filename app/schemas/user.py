from datetime import datetime
from typing import List, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator

from app.models.enums import UserRole
from app.models.user import AgentProfile
from app.schemas.common import (
    APIModel,
    TimestampedOut,
    normalize_email,
    validate_password_strength,
)


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str = Field(min_length=2, max_length=120)
    phone: Optional[str] = Field(None, max_length=30)
    role: UserRole = UserRole.AGENT
    permissions: List[str] = Field(default_factory=list)
    agent_profile: AgentProfile = Field(default_factory=AgentProfile)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validate_password_strength(v)


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=120)
    phone: Optional[str] = Field(None, max_length=30)
    avatar_media_id: Optional[PydanticObjectId] = None
    role: Optional[UserRole] = None
    permissions: Optional[List[str]] = None
    agent_profile: Optional[AgentProfile] = None
    is_active: Optional[bool] = None


class UserOut(TimestampedOut):
    tenant_id: PydanticObjectId
    email: str
    full_name: str
    phone: Optional[str] = None
    avatar_media_id: Optional[PydanticObjectId] = None
    role: UserRole
    permissions: List[str] = Field(default_factory=list)
    agent_profile: AgentProfile
    is_active: bool
    last_login_at: Optional[datetime] = None


class AgentPublicOut(APIModel):
    """Datos del agente visibles en el sitio público de la agencia."""

    id: PydanticObjectId
    full_name: str
    phone: Optional[str] = None
    avatar_media_id: Optional[PydanticObjectId] = None
    agent_profile: AgentProfile
