"""
Precision AI - Sign-in sessions, refresh-token rotation, revocation and account lockout.

  open_session    -> a new `auth_sessions` row + token pair (access carries `sid`, refresh carries `jti`)
  rotate          -> refresh: the presented `jti` must be the session's current one; it is replaced. Presenting
                     an already-used `jti` means the token was copied, so the whole session is revoked (except
                     within REUSE_GRACE_SECONDS of the rotation: two tabs refreshing at once get the current pair).
  revoke_*        -> logout, password change, deactivation
  lockout         -> failed sign-ins counted per identifier hash, including identifiers that match no user
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import create_access_token, create_refresh_token, new_token_id, refresh_lifetime
from app.database import utcnow
from app.models.auth import AuthSession, LoginThrottle
from app.models.user import User

logger = get_logger(__name__)
settings = get_settings()

REUSE_GRACE_SECONDS = 30


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class RefreshRejected(Exception):
    def __init__(self, reason: str, session: Optional[AuthSession] = None):
        super().__init__(reason)
        self.reason = reason
        self.session = session


# ---------------- sessions ----------------
def _token_pair(user: User, sid: str, jti: str) -> tuple[str, str]:
    access = create_access_token({"sub": str(user.id), "role": user.role_name, "sid": sid})
    refresh = create_refresh_token({"sub": str(user.id), "sid": sid, "jti": jti})
    return access, refresh


async def open_session(db: AsyncSession, user: User, ip_address: Optional[str]) -> tuple[str, str]:
    now = utcnow()
    session = AuthSession(id=new_token_id(), user_id=user.id, refresh_jti=new_token_id(), ip_address=ip_address,
                          created_at=now, expires_at=now + refresh_lifetime())
    db.add(session)
    await db.flush()
    return _token_pair(user, session.id, session.refresh_jti)


def session_is_live(session: Optional[AuthSession], user_id: int) -> bool:
    return (session is not None and session.revoked_at is None and session.user_id == user_id
            and _aware(session.expires_at) > utcnow())


async def rotate(db: AsyncSession, payload: dict) -> tuple[User, str, str]:
    sid, jti = payload.get("sid"), payload.get("jti")
    session = await db.get(AuthSession, sid) if isinstance(sid, str) else None
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise RefreshRejected("invalid")
    if not session_is_live(session, user_id):
        raise RefreshRejected("invalid")
    now = utcnow()
    racing = (jti is not None and jti == session.previous_jti and session.refreshed_at is not None
              and (now - _aware(session.refreshed_at)).total_seconds() <= REUSE_GRACE_SECONDS)
    if jti != session.refresh_jti and not racing:
        await revoke_session(db, session, "reuse")
        logger.warning("refresh_token_reuse", user_id=user_id)
        raise RefreshRejected("reuse", session)
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise RefreshRejected("inactive")
    if not racing:
        session.previous_jti, session.refresh_jti = session.refresh_jti, new_token_id()
        session.refreshed_at, session.expires_at = now, now + refresh_lifetime()
        await db.flush()
    access, refresh = _token_pair(user, session.id, session.refresh_jti)
    return user, access, refresh


async def revoke_session(db: AsyncSession, session: AuthSession, reason: str) -> None:
    if session.revoked_at is None:
        session.revoked_at, session.revoked_reason = utcnow(), reason
        await db.flush()


async def revoke_user_sessions(db: AsyncSession, user_id: int, reason: str) -> int:
    result = await db.execute(update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
                              .values(revoked_at=utcnow(), revoked_reason=reason))
    return int(result.rowcount or 0)


# ---------------- lockout ----------------
def throttle_key(identifier: str) -> str:
    return hashlib.sha256(identifier.strip().lower().encode("utf-8")).hexdigest()


async def _throttle_row(db: AsyncSession, key: str) -> LoginThrottle:
    row = (await db.execute(select(LoginThrottle).where(LoginThrottle.key == key))).scalar_one_or_none()
    if row is None:
        try:
            async with db.begin_nested():  # a parallel request may insert the same key first
                db.add(LoginThrottle(key=key, failures=0, window_start=utcnow()))
        except IntegrityError:
            pass
        row = (await db.execute(select(LoginThrottle).where(LoginThrottle.key == key))).scalar_one()
    return row


async def lockout_remaining(db: AsyncSession, key: str) -> Optional[int]:
    """Seconds left on an active lockout, or None."""
    row = (await db.execute(select(LoginThrottle).where(LoginThrottle.key == key))).scalar_one_or_none()
    if row is None or row.locked_until is None:
        return None
    left = (_aware(row.locked_until) - utcnow()).total_seconds()
    return int(left) + 1 if left > 0 else None


async def record_failure(db: AsyncSession, key: str) -> bool:
    """Count a failed sign-in; True when this failure starts a lockout."""
    now = utcnow()
    window = timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    row = await _throttle_row(db, key)
    if _aware(row.window_start) < now - window:
        row.failures, row.window_start, row.locked_until = 0, now, None
        await db.flush()
    # atomic increment, so parallel guesses cannot overwrite each other's count
    await db.execute(update(LoginThrottle).where(LoginThrottle.id == row.id)
                     .values(failures=LoginThrottle.failures + 1).execution_options(synchronize_session=False))
    await db.refresh(row)
    if row.failures >= settings.LOGIN_MAX_FAILURES and row.locked_until is None:
        row.locked_until = now + window
        await db.flush()
        return True
    return False


async def clear_failures(db: AsyncSession, key: str) -> None:
    await db.execute(delete(LoginThrottle).where(LoginThrottle.key == key))
