"""
Precision AI - Shared read endpoints: role-aware dashboard, notifications, reference data.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import incident_out, iso, ticket_out
from app.core.deps import get_current_user, is_staff
from app.database import get_db, utcnow
from app.agents.state_machine import PROGRESS_STEPS
from app.models.agent import AgentAction, AgentRun, Incident
from app.models.department import Department
from app.models.knowledge import KnowledgeDocument
from app.models.ticket import Ticket, TicketCategory, TicketEvent, TicketStatus
from app.models.user import User
from app.services import analytics
from app.services.correlation import as_aware

router = APIRouter(tags=["Dashboard & reference data"])

NOTIFY_EVENTS = ("status_changed", "escalated", "assigned", "linked_to_incident", "comment", "duplicate_linked")


@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    mine = Ticket.user_id == user.id

    async def count(*where) -> int:
        return int((await db.execute(select(func.count(Ticket.id)).where(*where))).scalar() or 0)

    recent = (await db.execute(select(Ticket).where(mine).order_by(Ticket.created_at.desc()).limit(5))).unique().scalars().all()
    incidents = (await db.execute(select(Incident).where(Incident.status.in_(("active", "investigating")))
                                  .order_by(Incident.last_reported.desc()).limit(3))).unique().scalars().all()
    inc_counts = dict((await db.execute(select(Ticket.incident_id, func.count(Ticket.id)).where(
        Ticket.incident_id.in_([i.id for i in incidents])).group_by(Ticket.incident_id))).all()) if incidents else {}
    resolved_rows = (await db.execute(select(Ticket.created_at, Ticket.resolved_at).where(
        mine, Ticket.status == TicketStatus.RESOLVED, Ticket.resolved_at.is_not(None)))).all()
    avg_minutes = None
    if resolved_rows:
        mins = [(as_aware(r[1]) - as_aware(r[0])).total_seconds() / 60 for r in resolved_rows]
        avg_minutes = round(sum(mins) / len(mins), 1)
    guides = (await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.is_active.is_(True))
                               .order_by(KnowledgeDocument.id).limit(4))).unique().scalars().all()
    pending_actions = (await db.execute(select(func.count(AgentAction.id)).join(Ticket, AgentAction.ticket_id == Ticket.id)
                                        .where(AgentAction.status == "pending_approval", mine))).scalar() or 0

    # Real agent pipeline progress for each recent ticket (share of checklist steps finished)
    progress: dict[int, int] = {}
    if recent:
        runs = (await db.execute(select(AgentRun).where(AgentRun.ticket_id.in_([t.id for t in recent]))
                                 .order_by(AgentRun.id))).scalars().all()
        for run in runs:
            steps = (run.context or {}).get("progress", {})
            done = sum(1 for s in steps.values() if s in ("done", "skipped"))
            progress[run.ticket_id] = round(done / len(PROGRESS_STEPS) * 100)

    out = {
        "user": {"name": user.full_name, "role": user.role_name},
        "my_tickets": {
            "open": await count(mine, Ticket.status.in_(TicketStatus.OPEN)),
            "in_analysis": await count(mine, Ticket.status.in_((TicketStatus.AI_ANALYSIS, TicketStatus.TROUBLESHOOTING))),
            "awaiting_me": await count(mine, Ticket.status == TicketStatus.AWAITING_USER) + int(pending_actions),
            "resolved": await count(mine, Ticket.status == TicketStatus.RESOLVED),
            "avg_resolution_minutes": avg_minutes,
        },
        "recent_tickets": [{**ticket_out(t), "pipeline_progress": progress.get(t.id)} for t in recent],
        "active_incidents": [incident_out(i, inc_counts.get(i.id, 0)) for i in incidents],
        "guides": [{"id": d.id, "title": d.title, "category": d.category.name if d.category else None,
                    "doc_type": d.doc_type} for d in guides],
    }
    if is_staff(user):
        out["support"] = await analytics.support_overview(db)
    return out


@router.get("/notifications")
async def notifications(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    since = utcnow() - timedelta(days=7)
    items = []
    q = (select(TicketEvent, Ticket.ticket_number).join(Ticket, TicketEvent.ticket_id == Ticket.id)
         .where(TicketEvent.created_at >= since, TicketEvent.event_type.in_(NOTIFY_EVENTS)))
    if is_staff(user):
        q = q.where(TicketEvent.event_type.in_(("escalated", "linked_to_incident")))
    else:
        q = q.where(Ticket.user_id == user.id, TicketEvent.user_id.is_distinct_from(user.id))
    for ev, number in (await db.execute(q.order_by(TicketEvent.id.desc()).limit(15))).all():
        items.append({"id": f"ev-{ev.id}", "type": ev.event_type, "ticket_id": ev.ticket_id, "ticket_number": number,
                      "message": ev.description or ev.event_type.replace("_", " "), "created_at": iso(ev.created_at)})
    pq = select(AgentAction).where(AgentAction.status == "pending_approval")
    if not is_staff(user):
        pq = pq.join(Ticket, AgentAction.ticket_id == Ticket.id).where(Ticket.user_id == user.id)
    for a in (await db.execute(pq.limit(10))).unique().scalars().all():
        items.append({"id": f"act-{a.id}", "type": "approval", "ticket_id": a.ticket_id,
                      "ticket_number": a.ticket.ticket_number,
                      "message": f"Approval required: {a.tool_name.replace('_', ' ')}", "created_at": iso(a.created_at)})
    for i in (await db.execute(select(Incident).where(Incident.status.in_(("active", "investigating")))
                               .limit(5))).unique().scalars().all():
        items.append({"id": f"inc-{i.id}", "type": "incident", "incident_id": i.id,
                      "message": f"{i.incident_number}: {i.title}", "created_at": iso(i.last_reported)})
    items.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return {"items": items[:25], "count": len(items)}


@router.get("/meta/categories")
async def categories(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(TicketCategory).where(TicketCategory.is_active.is_(True))
                             .order_by(TicketCategory.name))).unique().scalars().all()
    return [{"id": c.id, "name": c.name, "description": c.description,
             "department": c.department.name if c.department else None} for c in rows]


@router.get("/meta/departments")
async def departments(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Department).where(Department.is_active.is_(True))
                             .order_by(Department.name))).scalars().all()
    return [{"id": d.id, "name": d.name, "is_support_team": d.is_support_team} for d in rows]
