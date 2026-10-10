import os
import secrets
from typing import List


def _split(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    """Configuración leída de variables de entorno (Railway)."""

    def __init__(self) -> None:
        self.APP_NAME = os.getenv("APP_NAME", "SaaS Inmobiliario API")
        self.ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
        # En producción define JWT_SECRET; si no, se genera uno efímero.
        self.JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_urlsafe(48)
        self.ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
        self.REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "30"))
        self.CORS_ORIGINS = _split(os.getenv("CORS_ORIGINS", "*"))
        # Dominio base del SaaS: {slug}.BASE_DOMAIN identifica al tenant
        self.BASE_DOMAIN = (os.getenv("BASE_DOMAIN") or "").strip().lower()
        default_header = "false" if self.ENVIRONMENT == "production" else "true"
        # Permite elegir tenant con el header X-Tenant-Slug (solo desarrollo/pruebas)
        self.ALLOW_TENANT_HEADER = (
            os.getenv("ALLOW_TENANT_HEADER", default_header).lower() == "true"
        )
        # Railway expone MONGO_URL en su plantilla de MongoDB; MONGODB_URL tiene prioridad
        self.MONGODB_URL = (
            os.getenv("MONGODB_URL")
            or os.getenv("MONGO_URL")
            or "mongodb://localhost:27017"
        )
        self.MONGODB_DB = os.getenv("MONGODB_DB", "inmobiliaria_saas")
        self.SUPERADMIN_EMAIL = (os.getenv("SUPERADMIN_EMAIL") or "").strip().lower()
        self.SUPERADMIN_PASSWORD = os.getenv("SUPERADMIN_PASSWORD") or ""


settings = Settings()
