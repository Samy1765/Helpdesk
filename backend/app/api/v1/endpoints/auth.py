"""
Precision AI - Authentication: register, login (JSON + OAuth2 form), refresh, logout, profile.
Passwords are bcrypt-hashed; JWT access tokens are short-lived, refresh tokens longer-lived.
"""

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import user_out
from app.core.deps import get_current_user
from app.core.logging import get_logger
from app.core.security import (
    create_access_token, create_refresh_token, decode_token, hash_password, verify_password,
)
from app.database import get_db, utcnow
from app.models.department import Department
from app.models.user import Role, User
from app.services.tickets import audit

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = get_logger(__name__)


def _password_policy(v: str) -> str:
    if not (re.search(r"[A-Z]", v) and re.search(r"[a-z]", v) and re.search(r"\d", v)):
        raise ValueError("Password needs an uppercase letter, a lowercase letter and a digit")
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    department_id: Optional[int] = None
    job_title: Optional[str] = Field(default=None, max_length=150)

    @field_validator("username")
    @classmethod
    def username_chars(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.]+", v):
            raise ValueError("Username may contain letters, numbers, '.' and '_' only")
        return v.lower()

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        return _password_policy(v)


class LoginIn(BaseModel):
    username: str = Field(description="Username or email")
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class ProfileIn(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    job_title: Optional[str] = Field(default=None, max_length=150)
    location: Optional[str] = Field(default=None, max_length=150)
    department_id: Optional[int] = None


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        return _password_policy(v)


def _tokens(user: User) -> dict:
    data = {"sub": str(user.id), "role": user.role_name}
    return {"access_token": create_access_token(data), "refresh_token": create_refresh_token(data),
            "token_type": "bearer", "user": user_out(user)}


async def _authenticate(db: AsyncSession, identifier: str, password: str, request: Request) -> User:
    ident = identifier.strip().lower()
    user = (await db.execute(select(User).where(or_(User.username == ident, User.email == ident)))).unique().scalar_one_or_none()
    ip = request.client.host if request.client else None
    if not user or not verify_password(password, user.password_hash):
        await audit(db, "login_failed", resource_type="user", resource_id=user.id if user else None, ip_address=ip)
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is deactivated")
    user.last_login_at = utcnow()
    await audit(db, "login", user_id=user.id, resource_type="user", resource_id=user.id, ip_address=ip)
    return user


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Self-registration always creates an EMPLOYEE account; roles are granted by administrators."""
    exists = (await db.execute(select(User.id).where(or_(User.email == data.email.lower(),
                                                         User.username == data.username)))).first()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or username already registered")
    role = (await db.execute(select(Role).where(Role.name == "employee"))).scalar_one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Roles not seeded")
    if data.department_id is not None and await db.get(Department, data.department_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown department")
    user = User(email=data.email.lower(), username=data.username, password_hash=hash_password(data.password),
                full_name=data.full_name.strip(), role_id=role.id, department_id=data.department_id,
                job_title=data.job_title, last_login_at=utcnow())
    db.add(user)
    await db.flush()
    await db.refresh(user)
    await audit(db, "register", user_id=user.id, resource_type="user", resource_id=user.id,
                ip_address=request.client.host if request.client else None)
    logger.info("user_registered", user_id=user.id)
    return _tokens(user)


@router.post("/login")
async def login(data: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    return _tokens(await _authenticate(db, data.username, data.password, request))


@router.post("/token", include_in_schema=True, summary="OAuth2 password flow (used by Swagger 'Authorize')")
async def token(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    return _tokens(await _authenticate(db, form.username, form.password, request))


@router.post("/refresh")
async def refresh(data: RefreshIn, db: AsyncSession = Depends(get_db)):
    payload = decode_token(data.refresh_token, "refresh")
    user = await db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return _tokens(user)


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """JWTs are stateless: the client discards its tokens. The logout is recorded for auditing."""
    await audit(db, "logout", user_id=current_user.id, resource_type="user", resource_id=current_user.id)
    return {"message": "Logged out"}


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return user_out(current_user)


@router.patch("/me")
async def update_me(data: ProfileIn, current_user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await db.flush()
    await db.refresh(current_user)
    return user_out(current_user)


@router.post("/change-password")
async def change_password(data: PasswordIn, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    current_user.password_hash = hash_password(data.new_password)
    await audit(db, "password_changed", user_id=current_user.id, resource_type="user", resource_id=current_user.id)
    return {"message": "Password updated"}
