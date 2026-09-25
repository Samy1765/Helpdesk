"""
Precision AI - IT Support workspace: queue, ticket actions, knowledge curation.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import troubleshooting_agent as agent
from app.api.serializers import solution_out, ticket_out, user_out
from app.core.deps import STAFF_ROLES, require_role
from app.database import get_db
from app.models.ticket import SolutionConfidence, Ticket, TicketCategory, TicketSolution, TicketStatus
from app.models.user import Role, User
from app.services import analytics, knowledge, tickets as ticket_svc
from app.services.priority import LEVELS
from app.tools.registry import get_tool
from app.vector_store import get_index_manager

router = APIRouter(prefix="/support", tags=["IT Support"])
staff_only = require_role(*STAFF_ROLES)

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class AssignIn(BaseModel):
    user_id: int
    reason: str = Field(default="", max_length=500)


class StatusIn(BaseModel):
    status: Literal["in_progress", "awaiting_user", "escalated", "closed"]
    note: Optional[str] = Field(default=None, max_length=1000)


class StepIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    detail: str = Field(default="", max_length=4000)


class ResolveIn(BaseModel):
    resolution: str = Field(min_length=5, max_length=4000)
    root_cause: Optional[str] = Field(default=None, max_length=2000)
    steps: list[str] = Field(default_factory=list, max_length=15)
    save_as_knowledge: bool = True
    ai_solution_was_wrong: bool = False


class ClassificationIn(BaseModel):
    category_id: Optional[int] = None
    priority: Optional[Literal["low", "medium", "high", "critical"]] = None
    reason: str = Field(default="", max_length=500)


class SolutionIn(BaseModel):
    title: str = Field(min_length=5, max_length=300)
    problem_description: str = Field(min_length=10, max_length=4000)
    solution_description: str = Field(min_length=10, max_length=4000)
    steps: list[str] = Field(default_factory=list, max_length=15)
    category_id: int
    intent: Optional[str] = Field(default=None, max_length=120)
    root_cause: Optional[str] = Field(default=None, max_length=2000)
    automated_actions: list[str] = Field(default_factory=list, max_length=5)


async def _ticket(db: AsyncSession, ticket_id: int) -> Ticket:
    t = await ticket_svc.get_ticket(db, ticket_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return t


def _verified_level(user: User) -> str:
    return SolutionConfidence.ADMIN_VERIFIED if user.role_name == "admin" else SolutionConfidence.HUMAN_VERIFIED


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db), user: User = Depends(staff_only)):
    return await analytics.support_overview(db)


@router.get("/queue")
async def queue(
    view: Literal["unassigned", "mine", "escalated", "ai_active", "critical", "all_open", "resolved", "duplicates"] = "all_open",
    category: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = Query(100, ge=1, le=300),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(staff_only),
):
    q = select(Ticket)
    if view == "unassigned":
        q = q.where(Ticket.assigned_to.is_(None), Ticket.status.in_((TicketStatus.ESCALATED, TicketStatus.NEW)))
    elif view == "mine":
        q = q.where(Ticket.assigned_to == user.id, Ticket.status.in_(TicketStatus.OPEN))
    elif view == "escalated":
        q = q.where(Ticket.status.in_((TicketStatus.ESCALATED, TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS)))
    elif view == "ai_active":
        q = q.where(Ticket.status.in_((TicketStatus.AI_ANALYSIS, TicketStatus.TROUBLESHOOTING,
                                       TicketStatus.AWAITING_USER, TicketStatus.AWAITING_APPROVAL)))
    elif view == "critical":
        q = q.where(Ticket.priority.in_(("critical", "high")), Ticket.status.in_(TicketStatus.OPEN))
    elif view == "resolved":
        q = q.where(Ticket.status.in_((TicketStatus.RESOLVED, TicketStatus.CLOSED)))
    elif view == "duplicates":
        q = q.where((Ticket.status == TicketStatus.DUPLICATE) | Ticket.incident_id.is_not(None))
    else:
        q = q.where(Ticket.status.in_(TicketStatus.OPEN))
    if category:
        q = q.join(TicketCategory, Ticket.category_id == TicketCategory.id).where(TicketCategory.name == category)
    if priority:
        q = q.where(Ticket.priority == priority)
    rows = (await db.execute(q.order_by(Ticket.created_at.desc()).limit(limit))).unique().scalars().all()
    if view != "resolved":
        rows = sorted(rows, key=lambda t: (PRIORITY_ORDER.get(t.priority, 2), -t.id))
    return [ticket_out(t) for t in rows]


@router.get("/agents")
async def agents(db: AsyncSession = Depends(get_db), user: User = Depends(staff_only)):
    rows = (await db.execute(select(User).join(Role).where(Role.name.in_(STAFF_ROLES), User.is_active.is_(True))
                             .order_by(User.full_name))).unique().scalars().all()
    return [user_out(u) for u in rows]


@router.post("/tickets/{ticket_id}/accept")
async def accept(ticket_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(staff_only)):
    t = await _ticket(db, ticket_id)
    if t.status not in TicketStatus.OPEN:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ticket is closed")
    await agent.close_runs_for_human(db, t, f"Accepted by {user.full_name}")
    await ticket_svc.assign(db, t, user, by=user, reason="Accepted from queue")
    await ticket_svc.set_status(db, t, TicketStatus.IN_PROGRESS, user_id=user.id)
    await db.refresh(t)
    return ticket_out(t)


@router.post("/tickets/{ticket_id}/assign")
async def assign(ticket_id: int, data: AssignIn, db: AsyncSession = Depends(get_db), user: User = Depends(staff_only)):
    t = await _ticket(db, ticket_id)
    assignee = await db.get(User, data.user_id)
    if assignee is None or assignee.role_name not in STAFF_ROLES or not assignee.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Assignee must be an active IT staff member")
    await agent.close_runs_for_human(db, t, f"Assigned to {assignee.full_name}")
    await ticket_svc.assign(db, t, assignee, by=user, reason=data.reason)
    await db.refresh(t)
    return ticket_out(t)


@router.post("/tickets/{ticket_id}/status")
async def set_status(ticket_id: int, data: StatusIn, db: AsyncSession = Depends(get_db),
                     user: User = Depends(staff_only)):
    t = await _ticket(db, ticket_id)
    await ticket_svc.set_status(db, t, data.status, user_id=user.id, description=data.note or "")
    await db.refresh(t)
    return ticket_out(t)


@router.post("/tickets/{ticket_id}/steps", status_code=status.HTTP_201_CREATED)
async def add_step(ticket_id: int, data: StepIn, db: AsyncSession = Depends(get_db), user: User = Depends(staff_only)):
    t = await _ticket(db, ticket_id)
    await ticket_svc.add_step(db, t, step_key="manual", title=data.title, detail=data.detail,
                              performed_by="it_support", created_by=user.id)
    await ticket_svc.add_event(db, t, "troubleshooting_step", user_id=user.id, description=data.title)
    return {"message": "Step recorded"}


@router.post("/tickets/{ticket_id}/resolve")
async def resolve(ticket_id: int, data: ResolveIn, db: AsyncSession = Depends(get_db),
                  user: User = Depends(staff_only)):
    """Resolve as a human. Optionally store the fix as HUMAN/ADMIN-verified knowledge, and record
    whether the AI's proposal was wrong (that proposal is then rejected from retrieval)."""
    t = await _ticket(db, ticket_id)
    await agent.close_runs_for_human(db, t, f"Resolved by {user.full_name}")
    if data.ai_solution_was_wrong:
        for s in (await db.execute(select(TicketSolution).where(TicketSolution.ticket_id == t.id,
                                                                TicketSolution.source == "agent"))).unique().scalars():
            await knowledge.reject_solution(db, s, user)
        await ticket_svc.add_event(db, t, "ai_suggestion_rejected", user_id=user.id,
                                   description="IT marked the AI proposal as incorrect")
    t.resolution_summary = data.resolution
    t.resolved_by_ai = False
    if t.assigned_to is None:
        t.assigned_to = user.id
    await ticket_svc.set_status(db, t, TicketStatus.RESOLVED, user_id=user.id, description="Resolved by IT support")
    await ticket_svc.add_message(db, role="agent", content=f"Resolved: {data.resolution}", ticket_id=t.id,
                                 user_id=user.id)
    sol = None
    if data.save_as_knowledge:
        sol = await knowledge.capture_resolution(
            db, t, solution_text=data.resolution, steps=data.steps or knowledge.steps_from_text(data.resolution),
            confidence_level=_verified_level(user), source="it_support", root_cause=data.root_cause, user=user)
    await db.refresh(t)
    return {"ticket": ticket_out(t), "solution": solution_out(sol) if sol else None}


@router.patch("/tickets/{ticket_id}/classification")
async def correct_classification(ticket_id: int, data: ClassificationIn, db: AsyncSession = Depends(get_db),
                                 user: User = Depends(staff_only)):
    t = await _ticket(db, ticket_id)
    if data.category_id is not None and data.category_id != t.category_id:
        cat = await db.get(TicketCategory, data.category_id)
        if cat is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown category")
        await ticket_svc.add_event(db, t, "category_corrected", user_id=user.id, old_value=t.category_name,
                                   new_value=cat.name, description=data.reason or "Category corrected by IT")
        t.category_id = cat.id
        t.classification_method = "manual"
        t.department_id = cat.department_id or t.department_id
    if data.priority is not None and data.priority != t.priority:
        if data.priority not in LEVELS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown priority")
        await ticket_svc.add_event(db, t, "priority_corrected", user_id=user.id, old_value=t.priority,
                                   new_value=data.priority, description=data.reason or "Priority corrected by IT")
        t.priority = data.priority
    await db.flush()
    await db.refresh(t)
    await get_index_manager().index_ticket(t)
    return ticket_out(t)


# ---------------- knowledge curation ----------------
@router.get("/solutions")
async def list_solutions(level: Optional[str] = None, category_id: Optional[int] = None,
                         include_inactive: bool = False, db: AsyncSession = Depends(get_db),
                         user: User = Depends(staff_only)):
    q = select(TicketSolution)
    if level:
        q = q.where(TicketSolution.confidence_level == level)
    if category_id:
        q = q.where(TicketSolution.category_id == category_id)
    if not include_inactive:
        q = q.where(TicketSolution.is_active.is_(True))
    rows = (await db.execute(q.order_by(TicketSolution.created_at.desc()).limit(300))).unique().scalars().all()
    numbers = dict((await db.execute(select(Ticket.id, Ticket.ticket_number).where(
        Ticket.id.in_([s.ticket_id for s in rows if s.ticket_id])))).all())
    return [solution_out(s, numbers.get(s.ticket_id)) for s in rows]


@router.post("/solutions", status_code=status.HTTP_201_CREATED)
async def add_solution(data: SolutionIn, db: AsyncSession = Depends(get_db), user: User = Depends(staff_only)):
    if await db.get(TicketCategory, data.category_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown category")
    bad = [a for a in data.automated_actions if get_tool(a) is None]
    if bad:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown tools: {', '.join(bad)}")
    sol = await knowledge.create_solution(
        db, title=data.title, problem=data.problem_description, solution=data.solution_description,
        steps=data.steps or knowledge.steps_from_text(data.solution_description), category_id=data.category_id,
        intent=data.intent, confidence_level=_verified_level(user), source="admin" if user.role_name == "admin" else "it_support",
        root_cause=data.root_cause, automated_actions=data.automated_actions, created_by=user.id, verified_by=user.id)
    return solution_out(sol)


@router.post("/solutions/{solution_id}/verify")
async def verify_solution(solution_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(staff_only)):
    sol = await db.get(TicketSolution, solution_id)
    if sol is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Solution not found")
    await knowledge.promote_solution(db, sol, _verified_level(user), user)
    return solution_out(sol)


@router.post("/solutions/{solution_id}/reject")
async def reject_solution(solution_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(staff_only)):
    sol = await db.get(TicketSolution, solution_id)
    if sol is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Solution not found")
    await knowledge.reject_solution(db, sol, user)
    return solution_out(sol)
