"""
Precision AI - Administration: analytics, users, categories, system status, index maintenance, audit.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import iso, user_out
from app.core.config import get_settings
from app.core.deps import require_role
from app.database import get_db
from app.llm.router import available_tiers
from app.models.agent import AuditLog, LLMUsageLog
from app.models.department import Department
from app.models.ticket import TicketCategory
from app.models.user import Role, User
from app.services import analytics, tickets as ticket_svc
from app.vector_store import get_index_manager

router = APIRouter(prefix="/admin", tags=["Admin"])
admin_only = require_role("admin")
settings = get_settings()


class UserUpdate(BaseModel):
    role: Optional[Literal["employee", "it_support", "admin"]] = None
    is_active: Optional[bool] = None
    department_id: Optional[int] = None


class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    department_id: Optional[int] = None
    keywords: list[str] = Field(default_factory=list, max_length=60)


@router.get("/analytics")
async def get_analytics(days: int = Query(30, ge=7, le=365), db: AsyncSession = Depends(get_db),
                        user: User = Depends(admin_only)):
    return await analytics.admin_analytics(db, days)


@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db), user: User = Depends(admin_only)):
    rows = (await db.execute(select(User).order_by(User.created_at.desc()))).unique().scalars().all()
    return [user_out(u) for u in rows]


@router.patch("/users/{user_id}")
async def update_user(user_id: int, data: UserUpdate, db: AsyncSession = Depends(get_db),
                      admin: User = Depends(admin_only)):
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if target.id == admin.id and (data.role not in (None, "admin") or data.is_active is False):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot demote or deactivate yourself")
    changes = data.model_dump(exclude_unset=True)
    if data.role:
        role = (await db.execute(select(Role).where(Role.name == data.role))).scalar_one()
        target.role_id = role.id
    if data.is_active is not None:
        target.is_active = data.is_active
    if "department_id" in changes:
        target.department_id = data.department_id
    await ticket_svc.audit(db, "user_updated", user_id=admin.id, resource_type="user", resource_id=target.id,
                           details=changes)
    await db.flush()
    await db.refresh(target)
    return user_out(target)


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def create_category(data: CategoryIn, db: AsyncSession = Depends(get_db), admin: User = Depends(admin_only)):
    """Categories are data, not code: new ones are immediately used by the rule classifier."""
    if (await db.execute(select(TicketCategory).where(TicketCategory.name == data.name))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Category exists")
    cat = TicketCategory(name=data.name, description=data.description, department_id=data.department_id,
                         keywords=[k.lower().strip() for k in data.keywords if k.strip()])
    db.add(cat)
    await db.flush()
    await ticket_svc.audit(db, "category_created", user_id=admin.id, resource_type="category", resource_id=cat.id)
    return {"id": cat.id, "name": cat.name}


@router.get("/system")
async def system_status(user: User = Depends(admin_only)):
    return {
        "environment": settings.APP_ENV,
        "database": "sqlite" if settings.is_sqlite else "postgresql",
        "llm": {
            "small": {"provider": settings.LLM_SMALL_PROVIDER, "model": settings.LLM_SMALL_MODEL},
            "large": {"provider": settings.LLM_LARGE_PROVIDER, "model": settings.LLM_LARGE_MODEL},
            "available": await available_tiers(),
        },
        "vector_store": {"backend": "faiss", **get_index_manager().stats()},
        "thresholds": {
            "duplicate": settings.DUPLICATE_SIMILARITY_THRESHOLD, "solution_reuse": settings.SOLUTION_REUSE_THRESHOLD,
            "related": settings.RELATED_SIMILARITY_THRESHOLD, "kb_relevance": settings.KB_RELEVANCE_THRESHOLD,
            "incident": settings.INCIDENT_SIMILARITY_THRESHOLD,
        },
        "incident_window_minutes": settings.INCIDENT_WINDOW_MINUTES,
        "incident_min_tickets": settings.INCIDENT_MIN_TICKETS,
        "agent_max_attempts": settings.AGENT_MAX_ATTEMPTS,
        "diagnostic_tools_enabled": settings.AGENT_TOOLS_ENABLED,
    }


@router.post("/index/rebuild")
async def rebuild_index(db: AsyncSession = Depends(get_db), admin: User = Depends(admin_only)):
    report = await get_index_manager().rebuild_all(db)
    await ticket_svc.audit(db, "vector_index_rebuilt", user_id=admin.id, details=report)
    return report


@router.get("/audit-logs")
async def audit_logs(limit: int = Query(100, ge=1, le=500), db: AsyncSession = Depends(get_db),
                     user: User = Depends(admin_only)):
    rows = (await db.execute(select(AuditLog, User.full_name).outerjoin(User, AuditLog.user_id == User.id)
                             .order_by(AuditLog.id.desc()).limit(limit))).all()
    return [{"id": a.id, "action": a.action, "user": name, "resource_type": a.resource_type,
             "resource_id": a.resource_id, "details": a.details, "ip_address": a.ip_address,
             "created_at": iso(a.created_at)} for a, name in rows]


@router.get("/llm-calls")
async def llm_calls(limit: int = Query(50, ge=1, le=500), db: AsyncSession = Depends(get_db),
                    user: User = Depends(admin_only)):
    rows = (await db.execute(select(LLMUsageLog).order_by(LLMUsageLog.id.desc()).limit(limit))).scalars().all()
    return [{"id": r.id, "provider": r.provider, "model": r.model, "tier": r.tier, "purpose": r.purpose,
             "tokens": r.prompt_tokens + r.completion_tokens, "cost": r.estimated_cost, "cache_hit": r.cache_hit,
             "success": r.success, "error": r.error, "latency_ms": r.latency_ms, "ticket_id": r.ticket_id,
             "created_at": iso(r.created_at)} for r in rows]


@router.get("/departments")
async def departments(db: AsyncSession = Depends(get_db), user: User = Depends(admin_only)):
    rows = (await db.execute(select(Department).order_by(Department.name))).scalars().all()
    return [{"id": d.id, "name": d.name, "code": d.code, "is_support_team": d.is_support_team,
             "escalation_email": d.escalation_email} for d in rows]
