"""Mentis API — AI-powered AR Teacher backend.

Entry point for the FastAPI application.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import initialize_database, dispose_database
from app.core.logger import setup_logging, get_logger
from app.core.middleware import register_middleware

# Legacy routers (production, being migrated)
from app.routers import auth, tutor, streaming

# New API v1 routers (under construction)
from app.api.v1 import tutor as tutor_v1, vision as vision_v1, health as health_v1

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    log.info('app_starting', environment=settings.environment.value)
    await initialize_database()
    yield
    await dispose_database()
    log.info('app_stopped')


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=settings.app_description,
    lifespan=lifespan,
    docs_url='/docs' if settings.is_development else None,
    redoc_url='/redoc' if settings.is_development else None,
)

# ── CORS ───────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# ── Internal middleware (request ID, rate limit, timing) ──────────────
setup_logging()
register_middleware(app)

# ── Routers ────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(tutor.router)
app.include_router(streaming.router)

app.include_router(tutor_v1.router)
app.include_router(vision_v1.router)
app.include_router(health_v1.router)


# ── Root health check ─────────────────────────────────────────────────
@app.get('/health', tags=['health'])
async def health() -> dict:
    return {
        'status': 'ok',
        'version': settings.app_version,
        'environment': settings.environment.value,
    }
