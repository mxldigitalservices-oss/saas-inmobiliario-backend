import os
import secrets
from typing import List
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def _split(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_pg_url(url: str) -> str:
    """Convierte la URL de Railway al formato que exige SQLAlchemy + asyncpg.

    postgres://...      -> postgresql+asyncpg://...
    postgresql://...    -> postgresql+asyncpg://...
    Quita ?sslmode=... (asyncpg no lo acepta como parámetro de URL).
    """
    url = (url or "").strip()
    if not url:
        return ""
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix):]
            break
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() != "sslmode"]
    return urlunsplit(parts._replace(query=urlencode(query)))


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
        # PostgreSQL (Railway): DATABASE_URL tiene prioridad; si no existe, el servicio
        # PostgreSQL de Railway expone DATABASE_URL / POSTGRES_URL. Vacío = Postgres desactivado.
        self.DATABASE_URL = _normalize_pg_url(
            os.getenv("DATABASE_URL")
            or os.getenv("POSTGRES_URL")
            or os.getenv("POSTGRESQL_URL")
            or ""
        )
        self.PG_ECHO = os.getenv("PG_ECHO", "false").lower() == "true"
        self.PG_POOL_SIZE = int(os.getenv("PG_POOL_SIZE", "5"))
        self.PG_MAX_OVERFLOW = int(os.getenv("PG_MAX_OVERFLOW", "10"))
        # Solo para desarrollo: crea las tablas al arrancar. En producción usa migraciones.
        self.PG_AUTO_CREATE_TABLES = (
            os.getenv("PG_AUTO_CREATE_TABLES", "true").lower() == "true"
        )
        self.SUPERADMIN_EMAIL = (os.getenv("SUPERADMIN_EMAIL") or "").strip().lower()
        self.SUPERADMIN_PASSWORD = os.getenv("SUPERADMIN_PASSWORD") or ""


settings = Settings()
