"""
Precision AI - Core Configuration
Loads settings from environment variables with validation.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent

DEVELOPMENT_ENVS = ("development", "test")
# Values that appear in docs or defaults; never acceptable outside development
PLACEHOLDER_SECRETS = {"dev-secret-key-change-in-production", "change-me-to-a-64-char-random-string",
                       "changeme", "change-me", "secret", "secret-key"}
MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "PrecisionAI"
    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:5173"
    # Serve the built frontend (frontend/dist) from FastAPI when present
    SERVE_FRONTEND: bool = True
    FRONTEND_DIST_DIR: str = str(PROJECT_DIR / "frontend" / "dist")

    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # Sign-in lockout per username/email (unknown names included, so a lockout reveals nothing)
    LOGIN_MAX_FAILURES: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    # Per-process sliding-window budgets (the app runs one worker)
    RATE_LIMIT_LOGIN_FAILURES_PER_IP: int = 30   # failed sign-ins per client IP per 15 minutes
    RATE_LIMIT_REGISTER_PER_HOUR: int = 10       # self-registrations per client IP
    RATE_LIMIT_CHAT_PER_MINUTE: int = 20         # chat messages / portal tickets per user
    ALLOW_SELF_REGISTRATION: bool = True
    MAX_REQUEST_KB: int = 1024                   # JSON bodies; uploads are capped by MAX_UPLOAD_MB
    # Swagger / ReDoc / OpenAPI schema; blank = enabled everywhere except production
    API_DOCS_ENABLED: Optional[bool] = None
    # Seed the fictional demo company (python -m app.database.seed; the Docker entrypoint reads it too)
    SEED_DEMO_DATA: bool = False

    # Database. PostgreSQL is the primary target; SQLite is supported for local dev/tests.
    DATABASE_URL: str = "postgresql+asyncpg://precision_user:precision_pass@localhost:5432/precision_ai"
    DB_ECHO: bool = False

    # ---- LLM providers ----
    # Each provider's *_MODEL is its default; a tier uses it unless LLM_<TIER>_MODEL is set.
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"

    # Tiered routing: small (cheap/local) model for extraction + simple troubleshooting,
    # large model only for complex/ambiguous cases. Providers: ollama | groq | openai | gemini | none
    LLM_SMALL_PROVIDER: str = "ollama"
    LLM_SMALL_MODEL: str = ""  # blank = the provider's default model
    LLM_LARGE_PROVIDER: str = "groq"
    LLM_LARGE_MODEL: str = ""
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_RETRIES: int = 2
    LLM_CACHE_SIZE: int = 512
    # Reasoning models (gpt-oss, gpt-5, Gemini 2.5+/3) think before answering. Effort applies where the
    # API accepts it; the extra token budget keeps thinking from truncating the JSON answer.
    LLM_REASONING_EFFORT: str = "low"
    LLM_REASONING_EXTRA_TOKENS: int = 1024
    # Reference price (USD / 1K tokens) of the large model; used to estimate savings.
    # gpt-oss-120b on Groq: $0.15 in / $0.60 out per 1M, blended at ~4:1 input:output.
    LLM_REFERENCE_COST_PER_1K: float = 0.00024
    # Estimated tokens a full LLM troubleshooting call consumes when no measured data exists yet
    LLM_ESTIMATED_TOKENS_PER_CALL: int = 1200

    # ---- Embeddings / vector search ----
    # sentence-transformers (semantic, local, free) | hashing (dependency-free fallback)
    EMBEDDING_BACKEND: str = "sentence-transformers"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    FAISS_INDEX_DIR: str = str(PROJECT_DIR / "faiss_indexes")

    # Similarity thresholds (cosine), measured on all-MiniLM-L6-v2: paraphrased reports of the
    # same issue score 0.64-0.76, unrelated issues 0.09-0.22, related-but-different ~0.57.
    # Every similarity decision is additionally gated on matching category. See docs/ARCHITECTURE.md.
    DUPLICATE_SIMILARITY_THRESHOLD: float = 0.75
    SOLUTION_REUSE_THRESHOLD: float = 0.62
    RELATED_SIMILARITY_THRESHOLD: float = 0.45
    KB_RELEVANCE_THRESHOLD: float = 0.40
    # Near-identical reports may match across categories (guards against one misclassification)
    CROSS_CATEGORY_SIMILARITY: float = 0.85

    # ---- Incident correlation ----
    INCIDENT_WINDOW_MINUTES: int = 60
    INCIDENT_MIN_TICKETS: int = 3
    INCIDENT_SIMILARITY_THRESHOLD: float = 0.55

    # ---- Agent ----
    AGENT_MAX_ATTEMPTS: int = 2
    AGENT_TOOLS_ENABLED: bool = True
    SERVICE_CATALOG_FILE: str = str(PROJECT_DIR / "data" / "service_catalog.json")

    # ---- Attachments ----
    UPLOAD_DIR: str = str(PROJECT_DIR / "data" / "uploads")
    MAX_UPLOAD_MB: int = 5

    # ---- SLA targets (minutes to resolution, by effective priority) ----
    SLA_MINUTES: str = '{"critical": 60, "high": 240, "medium": 480, "low": 1440}'

    @property
    def sla_minutes(self) -> dict[str, int]:
        return json.loads(self.SLA_MINUTES)

    def tier_model(self, tier: str) -> str:
        """Model for a tier: LLM_<TIER>_MODEL, or the tier provider's default when blank, so switching
        LLM_LARGE_PROVIDER=openai never sends a Groq model name to OpenAI."""
        provider, model = ((self.LLM_SMALL_PROVIDER, self.LLM_SMALL_MODEL) if tier == "small"
                           else (self.LLM_LARGE_PROVIDER, self.LLM_LARGE_MODEL))
        if model.strip():
            return model.strip()
        return {"groq": self.GROQ_MODEL, "openai": self.OPENAI_MODEL, "gemini": self.GEMINI_MODEL,
                "ollama": self.OLLAMA_MODEL}.get((provider or "").lower(), "")

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "console"

    # CORS: only needed when the SPA is served from another origin (Vite proxies /api in development)
    CORS_ORIGINS: str = '["http://localhost:5173"]'

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return v
        return json.dumps(v)

    @field_validator("API_DOCS_ENABLED", mode="before")
    @classmethod
    def blank_means_default(cls, v):
        # `.env.example` ships `API_DOCS_ENABLED=`; docker compose passes that through as an empty string
        return None if isinstance(v, str) and not v.strip() else v

    @property
    def cors_origins_list(self) -> list[str]:
        return json.loads(self.CORS_ORIGINS)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV in DEVELOPMENT_ENVS

    @property
    def api_docs_enabled(self) -> bool:
        return self.API_DOCS_ENABLED if self.API_DOCS_ENABLED is not None else not self.is_production

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    model_config = {
        "env_file": (str(PROJECT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


def validate_settings(settings: Settings) -> None:
    """Refuse to start with development-only values anywhere except development and tests."""
    if settings.is_development:
        return
    key = settings.SECRET_KEY.strip()
    if key.lower() in PLACEHOLDER_SECRETS or key.startswith(("dev-", "change-me")) or len(key) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"SECRET_KEY is a placeholder or shorter than {MIN_SECRET_LENGTH} characters (APP_ENV={settings.APP_ENV}). "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\"")
    for origin in settings.cors_origins_list:
        if origin == "*" or not origin.startswith(("http://", "https://")) or origin.count("/") > 2:
            raise RuntimeError(f"CORS_ORIGINS must list exact origins such as https://helpdesk.example.com, got {origin!r}")


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()
    validate_settings(settings)
    return settings
