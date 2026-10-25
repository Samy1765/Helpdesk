"""
Precision AI - Authentication: register, login (JSON + OAuth2 form), refresh, logout, profile.
Passwords are bcrypt-hashed. Every sign-in opens a server-side session: access tokens are short-lived and tied
to it, refresh tokens rotate on each use, and logout / password changes revoke sessions immediately.
Failed sign-ins are throttled per identifier (lockout) and per client IP; error messages never reveal whether
an account exists.
"""

import asyncio
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import iso, user_out
from app.core.config import get_settings
from app.core.deps import get_current_session, get_current_user
from app.core.logging import get_logger
from app.core.ratelimit import enforce, limiter, too_many
from app.core.security import BCRYPT_MAX_BYTES, burn_password_check, decode_token, hash_password, verify_password
from app.database import get_db, utcnow
from app.models.auth import AuthSession
from app.models.department import Department
from app.models.user import Role, User
from app.services import auth as auth_svc
from app.services.tickets import audit

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = get_logger(__name__)
settings = get_settings()

INVALID_LOGIN = "Invalid username or password"
LOCKED = "Too many failed sign-in attempts. Try again in {minutes} min."
SESSION_ENDED = "Session expired or signed out"
IP_WINDOW_SECONDS = 15 * 60
PASSWORD_ATTEMPTS = 5


def _password_policy(v: str) -> str:
    if len(v.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes")
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
    username: str = Field(min_length=1, max_length=255, description="Username or email")
    password: str = Field(min_length=1, max_length=256)


class RefreshIn(BaseModel):
    refresh_token: str = Field(max_length=2048)


class ProfileIn(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    job_title: Optional[str] = Field(default=None, max_length=150)
    location: Optional[str] = Field(default=None, max_length=150)
    department_id: Optional[int] = None


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        return _password_policy(v)


def client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _token_body(user: User, access: str, refresh: str) -> dict:
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "user": user_out(user)}


async def _business_unit(db: AsyncSession, department_id: int) -> Department:
    """Employees pick their business unit; membership of an IT team is set by administrators."""
    dept = await db.get(Department, department_id)
    if dept is None or not dept.is_active or dept.is_support_team:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a business unit from the list")
    return dept


async def _authenticate(db: AsyncSession, identifier: str, password: str, request: Request) -> User:
    ident = identifier.strip().lower()[:255]
    ip = client_ip(request)
    ip_key = f"login-fail:{ip}"
    wait = limiter.retry_after(ip_key, settings.RATE_LIMIT_LOGIN_FAILURES_PER_IP, IP_WINDOW_SECONDS)
    if wait is not None:
        await audit(db, "login_failed", resource_type="user", ip_address=ip, details={"reason": "ip_rate_limited"})
        await db.commit()
        raise too_many(wait, "Too many failed sign-in attempts from this network. Try again later.")

    key = auth_svc.throttle_key(ident)
    locked_for = await auth_svc.lockout_remaining(db, key)
    if locked_for:
        await audit(db, "login_failed", resource_type="user", ip_address=ip, details={"reason": "locked"})
        await db.commit()
        raise too_many(locked_for, LOCKED.format(minutes=max(1, round(locked_for / 60))))

    user = (await db.execute(select(User).where(or_(User.username == ident, User.email == ident)))).unique().scalar_one_or_none()
    if user is None:
        await asyncio.to_thread(burn_password_check, password)
        valid = False
    else:
        valid = await asyncio.to_thread(verify_password, password, user.password_hash)
    if not valid:
        limiter.record(ip_key, IP_WINDOW_SECONDS)
        locked = await auth_svc.record_failure(db, key)
        await audit(db, "login_failed", resource_type="user", resource_id=user.id if user else None, ip_address=ip,
                    details={"reason": "bad_credentials"})
        if locked:
            await audit(db, "login_locked", resource_type="user", resource_id=user.id if user else None, ip_address=ip,
                        details={"minutes": settings.LOGIN_LOCKOUT_MINUTES})
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_LOGIN)
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is deactivated")
    await auth_svc.clear_failures(db, key)
    user.last_login_at = utcnow()
    await audit(db, "login", user_id=user.id, resource_type="user", resource_id=user.id, ip_address=ip)
    return user


async def _signed_in(db: AsyncSession, user: User, request: Request) -> dict:
    access, refresh = await auth_svc.open_session(db, user, client_ip(request))
    return _token_body(user, access, refresh)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Self-registration always creates an EMPLOYEE account; roles are granted by administrators."""
    if not settings.ALLOW_SELF_REGISTRATION:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Self-registration is turned off. Ask IT for an account.")
    enforce(f"register:{client_ip(request)}", settings.RATE_LIMIT_REGISTER_PER_HOUR, 3600,
            "Too many accounts created from this network. Try again later.")
    exists = (await db.execute(select(User.id).where(or_(User.email == data.email.lower(),
                                                         User.username == data.username)))).first()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or username already registered")
    role = (await db.execute(select(Role).where(Role.name == "employee"))).scalar_one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Roles not seeded")
    if data.department_id is not None:
        await _business_unit(db, data.department_id)
    user = User(email=data.email.lower(), username=data.username,
                password_hash=await asyncio.to_thread(hash_password, data.password),
                full_name=data.full_name.strip(), role_id=role.id, department_id=data.department_id,
                job_title=data.job_title, last_login_at=utcnow())
    db.add(user)
    await db.flush()
    await db.refresh(user)
    await audit(db, "register", user_id=user.id, resource_type="user", resource_id=user.id, ip_address=client_ip(request))
    logger.info("user_registered", user_id=user.id)
    return await _signed_in(db, user, request)


@router.post("/login")
async def login(data: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    return await _signed_in(db, await _authenticate(db, data.username, data.password, request), request)


@router.post("/token", include_in_schema=True, summary="OAuth2 password flow (used by Swagger 'Authorize')")
async def token(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    return await _signed_in(db, await _authenticate(db, form.username, form.password, request), request)


@router.post("/refresh")
async def refresh(data: RefreshIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Rotate the refresh token. A token that was already used revokes its session (it has been copied)."""
    payload = decode_token(data.refresh_token, "refresh")
    try:
        user, access, refresh_token = await auth_svc.rotate(db, payload)
    except auth_svc.RefreshRejected as exc:
        if exc.reason == "reuse" and exc.session is not None:
            await audit(db, "refresh_token_reuse", user_id=exc.session.user_id, resource_type="user",
                        resource_id=exc.session.user_id, ip_address=client_ip(request),
                        details={"session_created": iso(exc.session.created_at)})
            await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, SESSION_ENDED, headers={"WWW-Authenticate": "Bearer"})
    return _token_body(user, access, refresh_token)


@router.post("/logout")
async def logout(request: Request, session: AuthSession = Depends(get_current_session),
                 db: AsyncSession = Depends(get_db)):
    """Revoke this sign-in session: its access token and refresh token stop working immediately."""
    await auth_svc.revoke_session(db, session, "logout")
    await audit(db, "logout", user_id=session.user_id, resource_type="user", resource_id=session.user_id,
                ip_address=client_ip(request))
    return {"message": "Logged out"}


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return user_out(current_user)


@router.patch("/me")
async def update_me(data: ProfileIn, current_user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    changes = data.model_dump(exclude_unset=True)
    if "department_id" in changes and changes["department_id"] != current_user.department_id:
        if current_user.role_name != "employee":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "IT team membership is set by administrators")
        if changes["department_id"] is not None:
            await _business_unit(db, changes["department_id"])
    for field, value in changes.items():
        setattr(current_user, field, value)
    await db.flush()
    await db.refresh(current_user)
    return user_out(current_user)


@router.post("/change-password")
async def change_password(data: PasswordIn, request: Request, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Change the password, sign out every session and return tokens for a fresh one."""
    key = f"password-change:{current_user.id}"
    wait = limiter.retry_after(key, PASSWORD_ATTEMPTS, IP_WINDOW_SECONDS)
    if wait is not None:
        raise too_many(wait, "Too many incorrect attempts. Try again later.")
    if not await asyncio.to_thread(verify_password, data.current_password, current_user.password_hash):
        limiter.record(key, IP_WINDOW_SECONDS)
        await audit(db, "password_change_failed", user_id=current_user.id, resource_type="user",
                    resource_id=current_user.id, ip_address=client_ip(request))
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    current_user.password_hash = await asyncio.to_thread(hash_password, data.new_password)
    revoked = await auth_svc.revoke_user_sessions(db, current_user.id, "password_changed")
    access, refresh_token = await auth_svc.open_session(db, current_user, client_ip(request))
    await audit(db, "password_changed", user_id=current_user.id, resource_type="user", resource_id=current_user.id,
                ip_address=client_ip(request), details={"sessions_revoked": revoked})
    return {"message": "Password updated. Other devices have been signed out.",
            **_token_body(current_user, access, refresh_token)}
