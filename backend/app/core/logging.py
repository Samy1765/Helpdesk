"""
Precision AI - Structured Logging Configuration
Uses structlog for JSON/console structured logging.
Never logs passwords, API keys, tokens, or other secrets: a redaction processor
masks any event key that looks sensitive.
"""

import logging
import sys

import structlog

from app.core.config import get_settings

SENSITIVE_KEY_PARTS = ("password", "secret", "token", "api_key", "apikey", "authorization", "cookie")


def _redact_sensitive(_, __, event_dict: dict) -> dict:
    for key in list(event_dict.keys()):
        if any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
            event_dict[key] = "***redacted***"
    return event_dict


def setup_logging():
    """Configure structured logging for the application."""
    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_sensitive,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.LOG_FORMAT == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    for logger_name in ["uvicorn.access", "sqlalchemy.engine", "httpx", "sentence_transformers", "faiss"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)
