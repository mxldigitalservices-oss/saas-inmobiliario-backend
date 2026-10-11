import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.bootstrap import ensure_super_admin
from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.deps import tenant_from_host
from app.core.keepalive import start_keepalive, stop_keepalive
from app.core.redis_client import close_redis, get_redis, init_redis
from app.core.postgres_db import close_postgres, get_db, init_postgres
from app.routes import admin as admin_routes
from app.routes import auth as auth_routes
from app.routes import expense as expense_routes
from app.routes import health as health_routes
from app.routes import invoice as invoice_routes
from app.routes import media as media_routes
from app.routes import property as property_routes
from app.routes import tenant as tenant_routes
from app.routes import unit as unit_routes

logger = logging.getLogger("app")
API_PREFIX = "/api/v1"

# Carpeta del frontend (en la raíz del proyecto, junto a app/)
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
FRONTEND_PAGES = (
    "index",
    "dashboard",
    "properties",
    "units",
    "invoices",
    "settings",
    "admin",
    "public",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_postgres()
    await init_redis()
    start_keepalive()
    try:
        await ensure_super_admin()
    except Exception:  # pragma: no cover
        logger.exception("No se pudo crear el Super Admin inicial")
    yield
    await stop_keepalive()
    await close_redis()
    await close_postgres()
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="API REST multi-tenant (marca blanca) para agentes inmobiliarios.",
    lifespan=lifespan,
)

_allow_all = "*" in settings.CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_all else settings.CORS_ORIGINS,
    allow_credentials=not _allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_routes.router)
app.include_router(auth_routes.router, prefix=API_PREFIX)
app.include_router(tenant_routes.router, prefix=API_PREFIX)
app.include_router(admin_routes.router, prefix=API_PREFIX)
app.include_router(property_routes.router, prefix=API_PREFIX)
app.include_router(unit_routes.router, prefix=API_PREFIX)
app.include_router(media_routes.router, prefix=API_PREFIX)
app.include_router(invoice_routes.router, prefix=API_PREFIX)
app.include_router(expense_routes.router, prefix=API_PREFIX)


@app.get("/api", tags=["health"])
async def api_info():
    return {"name": settings.APP_NAME, "status": "ok", "docs": "/docs"}


# ------------------------------------------------------------------ Frontend
# Las rutas de la API y /docs se registran ANTES, así que nunca las pisa el frontend.
def _serve_page(name: str):
    def handler():
        path = FRONTEND_DIR / "{}.html".format(name)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Página no encontrada")
        # no-cache: el navegador revalida y siempre ve la última versión desplegada
        return FileResponse(path, media_type="text/html", headers={"Cache-Control": "no-cache"})

    return handler


def _page_response(name: str):
    path = FRONTEND_DIR / "{}.html".format(name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Página no encontrada")
    return FileResponse(path, media_type="text/html", headers={"Cache-Control": "no-cache"})


async def _root(request: Request):
    """"/" depende del dominio: si pertenece a una agencia (dominio propio verificado o
    {slug}.BASE_DOMAIN) se muestra SU catálogo público; en el host de la plataforma, el login."""
    try:
        tenant = await tenant_from_host(request)
    except Exception:  # pragma: no cover - nunca dejar sin login si falla la consulta
        logger.exception("No se pudo resolver la agencia del dominio")
        tenant = None
    return _page_response("public" if tenant is not None else "index")


app.add_api_route("/", _root, methods=["GET"], include_in_schema=False)

# El agente entra por /login (en un dominio de agencia "/" es el catálogo público)
app.add_api_route("/login", _serve_page("index"), methods=["GET"], include_in_schema=False)

# Catálogo público compartible en el host de la plataforma: /a/<agencia> y /a/<agencia>/<propiedad>
# (public.html lee el slug de la URL y lo envía como ?agency= a los endpoints públicos)
app.add_api_route("/a/{agency}", _serve_page("public"), methods=["GET"], include_in_schema=False)
app.add_api_route(
    "/a/{agency}/{prop_slug}", _serve_page("public"), methods=["GET"], include_in_schema=False
)

# Las páginas se enlazan entre sí con rutas relativas (dashboard.html, units.html...)
for _page in FRONTEND_PAGES:
    app.add_api_route(
        "/{}.html".format(_page),
        _serve_page(_page),
        methods=["GET"],
        include_in_schema=False,
    )

# Fotos y videos subidos (MEDIA_DIR) -> /files/tenants/{tenant_id}/{archivo}
_media_root = Path(settings.MEDIA_DIR).resolve()
try:
    _media_root.mkdir(parents=True, exist_ok=True)
except OSError:  # pragma: no cover
    logger.warning("No se pudo crear la carpeta de multimedia: %s", _media_root)
if _media_root.is_dir():
    app.mount("/files", StaticFiles(directory=str(_media_root)), name="media-files")

# Recursos propios (CSS/JS/imágenes) que agregues en frontend/ -> /static/...
if FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
else:  # pragma: no cover
    logger.warning("Carpeta frontend/ no encontrada: %s", FRONTEND_DIR)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


@app.get("/health/postgres", tags=["health"])
async def health_postgres(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "postgres": "connected"}


@app.get("/health/redis", tags=["health"])
async def health_redis(redis: Redis = Depends(get_redis)):
    try:
        await redis.ping()
    except Exception:
        raise HTTPException(status_code=503, detail="Redis no responde")
    return {"status": "ok", "redis": "connected"}
