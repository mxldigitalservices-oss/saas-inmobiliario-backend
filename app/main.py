import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.middleware.cors import CORSMiddleware

from app.core.bootstrap import ensure_super_admin
from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.postgres_db import close_postgres, get_db, init_postgres
from app.routes import admin as admin_routes
from app.routes import auth as auth_routes
from app.routes import expense as expense_routes
from app.routes import invoice as invoice_routes
from app.routes import property as property_routes
from app.routes import tenant as tenant_routes
from app.routes import unit as unit_routes

logger = logging.getLogger("app")
API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_postgres()
    try:
        await ensure_super_admin()
    except Exception:  # pragma: no cover
        logger.exception("No se pudo crear el Super Admin inicial")
    yield
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

app.include_router(auth_routes.router, prefix=API_PREFIX)
app.include_router(tenant_routes.router, prefix=API_PREFIX)
app.include_router(admin_routes.router, prefix=API_PREFIX)
app.include_router(property_routes.router, prefix=API_PREFIX)
app.include_router(unit_routes.router, prefix=API_PREFIX)
app.include_router(invoice_routes.router, prefix=API_PREFIX)
app.include_router(expense_routes.router, prefix=API_PREFIX)


@app.get("/", tags=["health"])
async def root():
    return {"name": settings.APP_NAME, "status": "ok", "docs": "/docs"}


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


@app.get("/health/postgres", tags=["health"])
async def health_postgres(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "postgres": "connected"}
