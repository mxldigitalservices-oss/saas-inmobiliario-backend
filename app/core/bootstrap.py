import logging

from app.core import security
from app.core.config import settings
from app.models.super_admin import SuperAdmin

logger = logging.getLogger("bootstrap")


async def ensure_super_admin() -> None:
    """Crea el Super Admin inicial desde SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD."""
    if not settings.SUPERADMIN_EMAIL or not settings.SUPERADMIN_PASSWORD:
        logger.info("SUPERADMIN_EMAIL/PASSWORD no definidos: se omite el bootstrap")
        return
    existing = await SuperAdmin.find_one({"email": settings.SUPERADMIN_EMAIL})
    if existing is not None:
        return
    admin = SuperAdmin(
        email=settings.SUPERADMIN_EMAIL,
        password_hash=security.hash_password(settings.SUPERADMIN_PASSWORD),
        full_name="Super Admin",
    )
    await admin.insert()
    logger.info("Super Admin inicial creado: %s", settings.SUPERADMIN_EMAIL)
