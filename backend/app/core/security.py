"""
Precision AI - Security utilities
JWT token management and password hashing (bcrypt directly; passwords are never stored in plaintext).

Every sign-in opens a server-side session (`auth_sessions`). Access tokens carry its id (`sid`) and are
rejected once the session is revoked; refresh tokens carry a one-time id (`jti`) that rotates on each use.
"""

import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

import bcrypt
import jwt
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import get_settings

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

BCRYPT_MAX_BYTES = 72  # bcrypt ignores (and bcrypt>=5 rejects) anything longer


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


@lru_cache()
def _dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def burn_password_check(password: str) -> None:
    """Spend the same bcrypt time as a real check, so unknown usernames are not revealed by timing."""
    verify_password(password, _dummy_hash())


def new_token_id() -> str:
    return secrets.token_urlsafe(16)


def _create_token(data: dict, token_type: str, expires: timedelta) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": datetime.now(timezone.utc) + expires, "type": token_type})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    return _create_token(data, "access",
                         expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(data: dict) -> str:
    return _create_token(data, "refresh", refresh_lifetime())


def refresh_lifetime() -> timedelta:
    return timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)


def decode_token(token: str, expected_type: str = "access") -> dict:
    """Decode and validate a JWT; rejects tokens of the wrong type (e.g. refresh used as access)."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM],
                             options={"require": ["exp", "sub", "type"]})
    except jwt.PyJWTError:
        payload = None
    if not payload or payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload
