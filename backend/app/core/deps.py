"""
Precision AI - FastAPI dependencies for authentication and role-based access.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token, oauth2_scheme
from app.database import get_db
from app.models.user import User

EMPLOYEE, IT_SUPPORT, ADMIN = "employee", "it_support", "admin"
STAFF_ROLES = (IT_SUPPORT, ADMIN)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(token, "access")
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
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
