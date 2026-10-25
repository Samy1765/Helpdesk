"""
Precision AI - FastAPI application
AI-Powered IT Helpdesk Ticketing, Troubleshooting and Autonomous Resolution System
"""

import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.middleware import BodySizeLimit, SecurityHeaders
from app.database import async_session_factory
from app.vector_store import get_index_manager

settings = get_settings()
logger = get_logger(__name__)

REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
UPLOAD_OVERHEAD_BYTES = 64 * 1024  # multipart boundaries and headers


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
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)

# Bearer tokens travel in a header, so CORS never needs credentials. Same-origin serving (and the Vite proxy in
# development) needs no CORS at all; listed origins are for a separately hosted frontend only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    max_age=600,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied = request.headers.get("x-request-id", "")
    request_id = supplied if REQUEST_ID.match(supplied) else uuid.uuid4().hex[:12]
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


app.add_middleware(BodySizeLimit, default_bytes=settings.MAX_REQUEST_KB * 1024,
                   upload_bytes=settings.MAX_UPLOAD_MB * 2**20 + UPLOAD_OVERHEAD_BYTES,
                   upload_paths=("/api/v1/attachments",))
app.add_middleware(SecurityHeaders)


@app.exception_handler(RequestValidationError)
async def validation_failed(request: Request, exc: RequestValidationError):
    """Like FastAPI's default, minus the echoed `input` (which would reflect submitted passwords)."""
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg", "Invalid value"), "type": e.get("type", "value_error")}
        for e in exc.errors()]})


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

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)  # HEAD: `curl -I`, uptime checks
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")
