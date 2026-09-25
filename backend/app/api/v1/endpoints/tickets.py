"""
Precision AI - Ticket endpoints (role-aware).
Employees see only their own tickets; IT support sees assigned/escalated work; admins see all.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import troubleshooting_agent as agent
from app.agents.state_machine import AgentState
from app.api.serializers import incident_out, iso, message_out, ticket_out
from app.core.deps import get_current_user, is_staff
from app.database import get_db
from app.models.agent import AgentAction, Incident
from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.ticket import (
    Ticket, TicketCategory, TicketEscalation, TicketEvent, TicketMessage, TicketStatus, TroubleshootingStep,
)
from app.models.user import User
from app.rag.retriever import similar_tickets
from app.services import classification as cls_svc, escalation, priority as prio_svc, tickets as ticket_svc
from app.tools.executor import action_view
from app.vector_store import get_index_manager
from app.vector_store.manager import ticket_text

router = APIRouter(prefix="/tickets", tags=["Tickets"])


class TicketIn(BaseModel):
    title: str = Field(min_length=5, max_length=300)
    description: str = Field(min_length=10, max_length=8000)
    user_priority: Optional[Literal["low", "medium", "high", "critical"]] = None


class FeedbackIn(BaseModel):
    resolved: bool
    comment: Optional[str] = Field(default=None, max_length=2000)


class CommentIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    internal: bool = False


async def load_ticket(db: AsyncSession, ticket_id: int, user: User) -> Ticket:
    ticket = await ticket_svc.get_ticket(db, ticket_id)
    if ticket is None or (not is_staff(user) and ticket.user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return ticket


def visibility_filter(user: User):
    if user.role_name == "employee":
        return Ticket.user_id == user.id
    if user.role_name == "it_support":
        clauses = [Ticket.assigned_to == user.id,
                   Ticket.status.in_((TicketStatus.ESCALATED, TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS)),
                   Ticket.priority == "critical", Ticket.user_id == user.id]
        return or_(*clauses)
    return None


@router.get("")
async def list_tickets(
    status_: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = None,
    priority: Optional[str] = None,
    q: Optional[str] = Query(None, max_length=100),
    scope: Literal["default", "all", "open", "closed"] = "default",
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Ticket)
    vis = visibility_filter(user)
    if vis is not None and not (scope == "all" and user.role_name == "it_support"):
        query = query.where(vis)
    if scope == "open":
        query = query.where(Ticket.status.in_(TicketStatus.OPEN))
    elif scope == "closed":
        query = query.where(Ticket.status.in_(TicketStatus.DONE))
    if status_:
        query = query.where(Ticket.status == status_)
    if category:
        query = query.join(TicketCategory, Ticket.category_id == TicketCategory.id).where(TicketCategory.name == category)
    if priority:
        query = query.where(Ticket.priority == priority)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Ticket.title.ilike(like), Ticket.ticket_number.ilike(like),
                                Ticket.description.ilike(like)))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (await db.execute(query.order_by(Ticket.created_at.desc(), Ticket.id.desc())
                             .offset((page - 1) * per_page).limit(per_page))).unique().scalars().all()
    return {"items": [ticket_out(t) for t in rows], "total": total, "page": page, "per_page": per_page}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_ticket(data: TicketIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Manual ticket (portal form). Goes through the same classification, priority and agent pipeline."""
    text = f"{data.title}. {data.description}"
    c = await cls_svc.classify(text, db)
    p = await prio_svc.assess_priority(text, db, category=c.category, entities=c.entities,
                                       user_priority=data.user_priority)
    ticket = await ticket_svc.create_ticket(
        db, user=user, title=data.title, description=data.description, category_id=c.category_id,
        sub_category=c.sub_category, intent=c.intent, entities=c.entities, ai_confidence=c.confidence,
        classification_method=c.method, user_priority=p.user_priority, system_priority=p.system_priority,
        priority_confidence=p.confidence, priority_reason=p.reason, priority_impact=p.impact,
        priority_urgency=p.urgency, source="portal",
    )
    await get_index_manager().index_ticket(ticket)
    alerts = [{"type": "warning", "message": p.alert}] if p.alert else []
    outcome = await agent.start(db, ticket, user, intake={"classification": c.as_dict(), "priority": p.as_dict(),
                                                          "alerts": alerts})
    await ticket_svc.add_message(db, role="assistant", content=outcome.message, ticket_id=ticket.id,
                                 payload={**outcome.payload, "quick_replies": outcome.quick_replies})
    await db.refresh(ticket)
    return {"ticket": ticket_out(ticket), "agent": {"state": outcome.state, "message": outcome.message,
                                                    "payload": outcome.payload}}


@router.get("/{ticket_id}")
async def ticket_detail(ticket_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = await load_ticket(db, ticket_id, user)
    staff = is_staff(user)
    msg_q = select(TicketMessage).where(TicketMessage.ticket_id == ticket.id)
    if not staff:
        msg_q = msg_q.where(TicketMessage.is_internal.is_(False))
    messages = (await db.execute(msg_q.order_by(TicketMessage.id))).unique().scalars().all()
    steps = (await db.execute(select(TroubleshootingStep).where(TroubleshootingStep.ticket_id == ticket.id)
                              .order_by(TroubleshootingStep.id))).scalars().all()
    events = (await db.execute(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)
                               .order_by(TicketEvent.id))).unique().scalars().all()
    actions = (await db.execute(select(AgentAction).where(AgentAction.ticket_id == ticket.id)
                                .order_by(AgentAction.id))).unique().scalars().all()
    run = await agent.active_run(db, ticket.id)
    current = (run.context or {}).get("current") if run and run.state == AgentState.VERIFY.value else None
    last_solution = current or next((m.payload.get("solution") for m in reversed(messages)
                                     if (m.payload or {}).get("solution")), None)
    esc = (await db.execute(select(TicketEscalation).where(TicketEscalation.ticket_id == ticket.id)
                            .order_by(TicketEscalation.id.desc()).limit(1))).unique().scalar_one_or_none()
    incident = await db.get(Incident, ticket.incident_id) if ticket.incident_id else None
    duplicate_of = await db.get(Ticket, ticket.duplicate_of_id) if ticket.duplicate_of_id else None
    attachments = (await db.execute(select(Attachment).where(Attachment.ticket_id == ticket.id))).scalars().all()
    similar = await similar_tickets(db, ticket_text(ticket), category_id=ticket.category_id,
                                    exclude_ticket_id=ticket.id, min_similarity=0.5, k=8)
    if not staff:
        similar = [h for h in similar if h.ticket.status in TicketStatus.DONE or h.ticket.user_id == user.id]

    return {
        "ticket": ticket_out(ticket),
        "messages": [message_out(m) for m in messages],
        "steps": [{"id": s.id, "key": s.step_key, "title": s.title, "detail": s.detail, "status": s.status,
                   "performed_by": s.performed_by, "created_at": iso(s.created_at)} for s in steps],
        "events": [{"id": e.id, "type": e.event_type, "description": e.description, "old": e.old_value,
                    "new": e.new_value, "actor": e.actor.full_name if e.actor else "System",
                    "created_at": iso(e.created_at)} for e in events],
        "agent": {
            "state": run.state, "attempt": run.attempt, "routing_level": run.routing_level,
            "llm_calls": run.llm_calls, "tokens_used": run.tokens_used, "confidence": run.confidence,
            "retrieval_hits": run.retrieval_hits, "retrieval": (run.context or {}).get("retrieval", []),
            "progress": agent.progress_view(run), "awaiting_feedback": run.state == AgentState.VERIFY.value,
            "reasoning_summary": run.reasoning_summary if staff else None,
            "resolution_status": run.resolution_status,
        } if run else None,
        "solution": last_solution,
        "actions": [action_view(a) for a in actions],
        "escalation": {"department": esc.department.name, "reason": esc.reason,
                       "package": esc.package if staff else None, "created_at": iso(esc.created_at)} if esc else None,
        "incident": incident_out(incident) if incident else None,
        "duplicate_of": {"id": duplicate_of.id, "ticket_number": duplicate_of.ticket_number,
                         "title": duplicate_of.title} if duplicate_of else None,
        "similar": [{"id": h.ticket.id, "ticket_number": h.ticket.ticket_number, "title": h.ticket.title,
                     "status": h.ticket.status, "similarity": round(h.similarity, 3)} for h in similar[:5]],
        "attachments": [{"token": a.token, "filename": a.filename, "content_type": a.content_type,
                         "size": a.size_bytes} for a in attachments],
        "can_manage": staff,
    }


@router.post("/{ticket_id}/feedback")
async def feedback(ticket_id: int, data: FeedbackIn, db: AsyncSession = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """The requester confirms whether the proposed fix worked (drives RESOLVED / RETRY / ESCALATE)."""
    ticket = await load_ticket(db, ticket_id, user)
    if ticket.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the requester can confirm a fix")
    try:
        outcome = await agent.handle_feedback(db, ticket, user, data.resolved, data.comment)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    conv_id = (await db.execute(select(Conversation.id).where(Conversation.ticket_id == ticket.id))).scalar()
    await ticket_svc.add_message(db, role="user", content="Yes, it's fixed" if data.resolved else
                                 f"No, still not working{': ' + data.comment if data.comment else ''}",
                                 ticket_id=ticket.id, conversation_id=conv_id, user_id=user.id)
    await ticket_svc.add_message(db, role="assistant", content=outcome.message, ticket_id=ticket.id,
                                 conversation_id=conv_id,
                                 payload={**outcome.payload, "quick_replies": outcome.quick_replies})
    if outcome.conversation_done and conv_id:
        conv = await db.get(Conversation, conv_id)
        if conv and conv.status == "active":
            conv.status, conv.stage = "closed", "closed"
    await db.refresh(ticket)
    return {"ticket": ticket_out(ticket), "agent": {"state": outcome.state, "message": outcome.message,
                                                    "payload": outcome.payload}}


@router.post("/{ticket_id}/comments", status_code=status.HTTP_201_CREATED)
async def comment(ticket_id: int, data: CommentIn, db: AsyncSession = Depends(get_db),
                  user: User = Depends(get_current_user)):
    ticket = await load_ticket(db, ticket_id, user)
    staff = is_staff(user)
    if data.internal and not staff:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only IT staff can add internal notes")
    msg = await ticket_svc.add_message(db, role="agent" if staff else "user", content=data.content,
                                       ticket_id=ticket.id, user_id=user.id, is_internal=data.internal)
    await ticket_svc.add_event(db, ticket, "internal_note" if data.internal else "comment", user_id=user.id,
                               description=data.content[:300])
    await db.refresh(msg)
    return message_out(msg)


@router.post("/{ticket_id}/request-human")
async def request_human(ticket_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = await load_ticket(db, ticket_id, user)
    if ticket.status not in TicketStatus.OPEN:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ticket is closed")
    if ticket.status in (TicketStatus.ESCALATED, TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS):
        return {"ticket": ticket_out(ticket), "message": "A human agent already owns this ticket"}
    run = await agent.active_run(db, ticket.id)
    await agent.close_runs_for_human(db, ticket, "Employee requested a human agent")
    await escalation.escalate(db, ticket, reason="Employee requested a human IT agent", run=run, actor_id=user.id)
    await db.refresh(ticket)
    return {"ticket": ticket_out(ticket), "message": f"Escalated to {ticket.department.name if ticket.department else 'IT'}"}
