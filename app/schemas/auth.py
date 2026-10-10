from typing import List, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import UserRole
from app.models.tenant import SLUG_REGEX
from app.schemas.common import APIModel, normalize_email, validate_password_strength


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)


class SuperAdminLoginRequest(LoginRequest):
    otp_code: Optional[str] = Field(None, min_length=6, max_length=8)


class RegisterTenantRequest(BaseModel):
    """Registro self-service de una nueva agencia (con token de activación opcional)."""

    agency_name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=3, max_length=63)
    owner_full_name: str = Field(min_length=2, max_length=120)
    owner_email: str
    password: str
    phone: Optional[str] = Field(None, max_length=30)
    activation_token: Optional[str] = Field(None, min_length=8, max_length=128)

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        v = v.strip().lower()
        if not SLUG_REGEX.match(v):
            raise ValueError("Slug inválido: use minúsculas, números y guiones")
        return v

    @field_validator("owner_email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validate_password_strength(v)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int = Field(description="Segundos hasta que expire el access token")


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class TokenPayload(BaseModel):
    """Contenido (claims) del JWT."""

    sub: str
    aud: str = "tenant"  # "tenant" | "superadmin"
    type: str = "access"  # "access" | "refresh"
    tenant_id: Optional[str] = None
    role: Optional[str] = None
    exp: int
    iat: Optional[int] = None
    jti: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validate_password_strength(v)

    @model_validator(mode="after")
    def _different(self):
        if self.current_password == self.new_password:
            raise ValueError("La nueva contraseña debe ser distinta a la actual")
        return self


class CurrentUserOut(APIModel):
    id: PydanticObjectId
    email: str
    full_name: str
    role: UserRole
    tenant_id: PydanticObjectId
    permissions: List[str] = Field(default_factory=list)
    tenant_read_only: bool = False
