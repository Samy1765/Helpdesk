"""
Precision AI - FastAPI dependencies for authentication and role-based access.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token, oauth2_scheme
from app.database import get_db
from app.models.auth import AuthSession
from app.models.user import User
from app.services.auth import session_is_live

EMPLOYEE, IT_SUPPORT, ADMIN = "employee", "it_support", "admin"
STAFF_ROLES = (IT_SUPPORT, ADMIN)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail,
                         headers={"WWW-Authenticate": "Bearer"})


async def get_current_session(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthSession:
    """The live sign-in session behind an access token (revoked by logout or a password change)."""
    payload = decode_token(token, "access")
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise _unauthorized("Invalid token payload")
    sid = payload.get("sid")
    session = await db.get(AuthSession, sid) if isinstance(sid, str) else None
    if not session_is_live(session, user_id):
        raise _unauthorized("Session expired or signed out")
    return session


async def get_current_user(
    session: AuthSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = (await db.execute(select(User).where(User.id == session.user_id))).unique().scalar_one_or_none()
    if not user:
        raise _unauthorized("User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")
    return user


def require_role(*roles: str):
    """Dependency factory: allow only the given roles."""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role_name not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Requires role: {', '.join(roles)}")
        return current_user
    return role_checker


def is_staff(user: User) -> bool:
    return user.role_name in STAFF_ROLES
