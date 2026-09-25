"""
Precision AI - Escalation Engine.
Routes unresolved tickets to the department that owns their category (ticket_categories ->
departments), builds an escalation package with evidence and a concise decision summary
(never hidden reasoning), and auto-assigns the least-loaded active agent of that team.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.agent import AgentAction, AgentRun
from app.models.department import Department
from app.models.ticket import Ticket, TicketEscalation, TicketStatus, TroubleshootingStep
from app.models.user import Role, User
from app.services import tickets as ticket_svc

logger = get_logger(__name__)

FALLBACK_DEPARTMENT_CODE = "SERVICE_DESK"


async def department_for(db: AsyncSession, ticket: Ticket) -> Department:
    if ticket.category and ticket.category.department_id:
        dept = await db.get(Department, ticket.category.department_id)
        if dept and dept.is_active:
            return dept
    dept = (await db.execute(select(Department).where(Department.code == FALLBACK_DEPARTMENT_CODE))).scalar_one_or_none()
    if dept is None:
        raise RuntimeError("No fallback Service Desk department configured (run the seed)")
    return dept


async def build_package(db: AsyncSession, ticket: Ticket, run: Optional[AgentRun], dept: Department,
                        reason: str) -> dict:
    steps = (await db.execute(select(TroubleshootingStep).where(TroubleshootingStep.ticket_id == ticket.id)
                              .order_by(TroubleshootingStep.id))).scalars().all()
    actions = []
    if run is not None:
        actions = (await db.execute(select(AgentAction).where(AgentAction.agent_run_id == run.id))).unique().scalars().all()
    ctx = (run.context or {}) if run else {}
    return {
        "ticket_id": ticket.ticket_number,
        "summary": ticket.title,
        "description": ticket.description[:2000],
        "category": ticket.category_name,
        "intent": ticket.intent,
        "priority": ticket.priority,
        "user_priority": ticket.user_priority,
        "entities": ticket.entities or {},
        "troubleshooting_attempted": [
            {"title": c.get("title"), "label": c.get("label"), "steps": c.get("steps", [])[:6],
             "outcome": "not resolved"} for c in ctx.get("tried", [])
        ],
        "diagnostics": [
            {"tool": a.tool_name, "status": a.status, "result": (a.result or {}).get("summary")} for a in actions
        ],
        "retrieved_solutions": ctx.get("retrieval", [])[:5],
        "agent_reasoning_summary": (run.reasoning_summary if run and run.reasoning_summary else reason),
        "timeline": [{"step": s.title, "status": s.status, "at": s.created_at.isoformat() if s.created_at else None}
                     for s in steps][-12:],
        "user_information": {
            "name": ticket.creator.full_name if ticket.creator else None,
            "department": ticket.creator.department.name if ticket.creator and ticket.creator.department else None,
            "location": ticket.creator.location if ticket.creator else None,
        },
        "recommended_department": dept.name,
        "escalation_reason": reason,
    }


async def least_loaded_agent(db: AsyncSession, dept: Department) -> Optional[User]:
    open_count = (select(Ticket.assigned_to, func.count(Ticket.id).label("n"))
                  .where(Ticket.status.in_(TicketStatus.OPEN)).group_by(Ticket.assigned_to).subquery())
    q = (select(User).join(Role).outerjoin(open_count, open_count.c.assigned_to == User.id)
         .where(User.department_id == dept.id, User.is_active.is_(True), Role.name.in_(("it_support", "admin")))
         .order_by(func.coalesce(open_count.c.n, 0), User.id).limit(1))
    return (await db.execute(q)).unique().scalar_one_or_none()


async def escalate(db: AsyncSession, ticket: Ticket, *, reason: str, run: Optional[AgentRun] = None,
                   actor_id: Optional[int] = None, auto_assign: bool = True) -> TicketEscalation:
    dept = await department_for(db, ticket)
    package = await build_package(db, ticket, run, dept, reason)
    esc = TicketEscalation(ticket_id=ticket.id, department_id=dept.id, reason=reason, package=package)
    db.add(esc)
    ticket.department_id = dept.id
    await ticket_svc.set_status(db, ticket, TicketStatus.ESCALATED, user_id=actor_id,
                                description=f"Escalated to {dept.name}: {reason}")
    await ticket_svc.add_event(db, ticket, "escalated", user_id=actor_id, new_value=dept.name, description=reason)
    if auto_assign and ticket.assigned_to is None:
        agent = await least_loaded_agent(db, dept)
        if agent:
            await ticket_svc.assign(db, ticket, agent, by=None, reason=f"Auto-assigned on escalation to {dept.name}")
    await db.flush()
    logger.info("ticket_escalated", ticket_id=ticket.id, department=dept.name, reason=reason,
                agent_run_id=run.id if run else None, assigned_to=ticket.assigned_to)
    return esc
