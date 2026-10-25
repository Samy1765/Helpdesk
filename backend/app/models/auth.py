"""
Precision AI - Sign-in sessions and login throttling.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base, utcnow


class AuthSession(Base):
    """One signed-in device. Revoking it invalidates its access tokens and its refresh-token chain."""
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # `sid` claim
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    refresh_jti: Mapped[str] = mapped_column(String(32))  # the only refresh token id still accepted
    # The id it replaced, accepted for a few seconds so parallel refreshes from one client do not end the session
    previous_jti: Mapped[Optional[str]] = mapped_column(String(32))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    refreshed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[Optional[str]] = mapped_column(String(40))  # logout | password_changed | reuse | deactivated


class LoginThrottle(Base):
    """Failed sign-ins per identifier. `key` is a hash, so mistyped passwords in the username box are not stored."""
    __tablename__ = "login_throttle"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    failures: Mapped[int] = mapped_column(default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
