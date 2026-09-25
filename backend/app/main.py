"""
Precision AI - FastAPI application
AI-Powered IT Helpdesk Ticketing, Troubleshooting and Autonomous Resolution System
"""

import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.database import async_session_factory
from app.vector_store import get_index_manager

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("starting_precision_ai", env=settings.APP_ENV,
                database="sqlite" if settings.is_sqlite else "postgresql")
    async with async_session_factory() as db:
        # Schema is managed by Alembic (`alembic upgrade head`); fail fast with a clear message.
        try:
            await db.execute(text("SELECT 1 FROM users LIMIT 1"))
        except Exception as exc:
            logger.error("database_not_migrated", hint="run: alembic upgrade head && python -m app.database.seed",
                         error=str(exc)[:200])
            raise
        await get_index_manager().initialize(db)
    yield
    logger.info("shutting_down_precision_ai")


app = FastAPI(
    title="Precision AI",
    description=("AI-Powered IT Helpdesk Ticketing, Troubleshooting and Autonomous Resolution System. "
                 "Authenticate with **Authorize** (username/password) to try the endpoints."),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    structlog.contextvars.bind_contextvars(request_id=request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        structlog.contextvars.clear_contextvars()
    response.headers["x-request-id"] = request_id
    if request.url.path.startswith("/api/"):
        logger.info("http_request", method=request.method, path=request.url.path, status=response.status_code,
                    latency_ms=round((time.perf_counter() - start) * 1000, 1), request_id=request_id)
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logger.exception("unhandled_error", path=request.url.path, error_type=type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(api_router)


@app.get("/health", tags=["Health"])
async def health():
    async with async_session_factory() as db:
        await db.execute(text("SELECT 1"))
    return {"status": "healthy", "service": "precision-ai", "vector_indexes": get_index_manager().stats()["indexes"]}


# ---- Serve the built React app (single-origin deployment) ----
dist = Path(settings.FRONTEND_DIST_DIR)
if settings.SERVE_FRONTEND and (dist / "index.html").exists():
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")
