"""
Precision AI - Ticket service: creation, status changes, messages, events, steps.
All writes happen inside the caller's transaction (the request-scoped session).
"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database import utcnow
from app.models.agent import AuditLog
from app.models.ticket import (
    Ticket, TicketAssignment, TicketEvent, TicketMessage, TicketStatus, TroubleshootingStep,
)
from app.models.user import User

logger = get_logger(__name__)


async def create_ticket(
    db: AsyncSession,
    *,
    user: User,
    title: str,
    description: str,
    category_id: Optional[int],
    sub_category: Optional[str] = None,
    intent: Optional[str] = None,
    entities: Optional[dict] = None,
    ai_confidence: Optional[float] = None,
    classification_method: Optional[str] = None,
    user_priority: Optional[str] = None,
    system_priority: Optional[str] = None,
    priority_confidence: Optional[float] = None,
    priority_reason: Optional[str] = None,
    priority_impact: Optional[str] = None,
    priority_urgency: Optional[str] = None,
    status: str = TicketStatus.AI_ANALYSIS,
    source: str = "ai_chatbot",
    extra_data: Optional[dict] = None,
) -> Ticket:
    ticket = Ticket(
        ticket_number=f"TMP-{uuid.uuid4().hex[:12]}",
        user_id=user.id, title=title[:300], description=description,
        category_id=category_id, sub_category=sub_category, intent=intent, entities=entities or {},
        ai_confidence=ai_confidence, classification_method=classification_method,
        user_priority=user_priority, system_priority=system_priority,
        # Effective priority follows the validated assessment; the user's value is kept and shown
        priority=system_priority or user_priority or "medium",
        priority_confidence=priority_confidence, priority_reason=priority_reason,
        priority_impact=priority_impact, priority_urgency=priority_urgency,
        status=status, source=source, extra_data=extra_data or {},
    )
    db.add(ticket)
    await db.flush()
    ticket.ticket_number = f"INC-{ticket.id:06d}"  # sequential, derived from the PK
    await add_event(db, ticket, "ticket_created", user_id=user.id, new_value=ticket.status,
                    description=f"Ticket created via {source}")
    await db.flush()
    await db.refresh(ticket)
    logger.info("ticket_created", ticket_id=ticket.id, ticket_number=ticket.ticket_number,
                category_id=category_id, priority=ticket.priority)
    return ticket


async def get_ticket(db: AsyncSession, ticket_id: int) -> Optional[Ticket]:
    return (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).unique().scalar_one_or_none()


async def get_ticket_by_number(db: AsyncSession, number: str) -> Optional[Ticket]:
    return (await db.execute(select(Ticket).where(Ticket.ticket_number == number))).unique().scalar_one_or_none()


async def add_event(db: AsyncSession, ticket: Ticket, event_type: str, *, user_id: Optional[int] = None,
                    old_value=None, new_value=None, description: str = "") -> TicketEvent:
    ev = TicketEvent(ticket_id=ticket.id, user_id=user_id, event_type=event_type,
                     old_value=None if old_value is None else str(old_value)[:300],
                     new_value=None if new_value is None else str(new_value)[:300],
                     description=description)
    db.add(ev)
    return ev


async def set_status(db: AsyncSession, ticket: Ticket, status: str, *, user_id: Optional[int] = None,
                     description: str = "") -> None:
    if status not in TicketStatus.ALL:
        raise ValueError(f"Unknown ticket status {status}")
    if ticket.status == status:
        return
    old = ticket.status
    ticket.status = status
    if status in (TicketStatus.RESOLVED, TicketStatus.CLOSED) and not ticket.resolved_at:
        ticket.resolved_at = utcnow()
    elif status in TicketStatus.OPEN:
        ticket.resolved_at = None
    await add_event(db, ticket, "status_changed", user_id=user_id, old_value=old, new_value=status,
                    description=description or f"Status {old} -> {status}")


async def add_message(db: AsyncSession, *, role: str, content: str, ticket_id: Optional[int] = None,
                      conversation_id: Optional[int] = None, user_id: Optional[int] = None,
                      payload: Optional[dict] = None, is_internal: bool = False) -> TicketMessage:
    msg = TicketMessage(ticket_id=ticket_id, conversation_id=conversation_id, user_id=user_id, role=role,
                        content=content, payload=payload or {}, is_internal=is_internal)
    db.add(msg)
    await db.flush()
    return msg


async def add_step(db: AsyncSession, ticket: Ticket, *, step_key: str, title: str, detail: str = "",
                   status: str = "completed", performed_by: str = "agent", agent_run_id: Optional[int] = None,
                   created_by: Optional[int] = None) -> TroubleshootingStep:
    step = TroubleshootingStep(ticket_id=ticket.id, agent_run_id=agent_run_id, step_key=step_key,
                               title=title[:200], detail=detail, status=status,
                               performed_by=performed_by, created_by=created_by)
    db.add(step)
    return step


async def assign(db: AsyncSession, ticket: Ticket, assignee: User, *, by: Optional[User], reason: str = "") -> None:
    ticket.assigned_to = assignee.id
    if assignee.department_id and not ticket.department_id:
        ticket.department_id = assignee.department_id
    db.add(TicketAssignment(ticket_id=ticket.id, assigned_by=by.id if by else None,
                            assigned_to=assignee.id, reason=reason[:500]))
    await add_event(db, ticket, "assigned", user_id=by.id if by else None, new_value=assignee.full_name,
                    description=reason or f"Assigned to {assignee.full_name}")
    if ticket.status in (TicketStatus.NEW, TicketStatus.ESCALATED, TicketStatus.AI_ANALYSIS,
                         TicketStatus.AWAITING_USER, TicketStatus.TROUBLESHOOTING):
        await set_status(db, ticket, TicketStatus.ASSIGNED, user_id=by.id if by else None)


async def audit(db: AsyncSession, action: str, *, user_id: Optional[int] = None, resource_type: str = "",
                resource_id: Optional[int] = None, details: Optional[dict] = None,
                ip_address: Optional[str] = None) -> None:
    db.add(AuditLog(user_id=user_id, action=action, resource_type=resource_type, resource_id=resource_id,
                    details=details or {}, ip_address=ip_address))
