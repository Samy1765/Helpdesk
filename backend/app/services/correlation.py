"""
Precision AI - Duplicate detection and Incident Correlation Engine.

Duplicate detection (semantic, FAISS):
  1. same user + open ticket about the same issue  -> new ticket marked DUPLICATE of the original
  2. different users + same issue in a time window -> incident correlation (below)
  3. similar historical issues                      -> surfaced through retrieval

Incident correlation: when >= INCIDENT_MIN_TICKETS reports from distinct users in the same
category are semantically similar within INCIDENT_WINDOW_MINUTES, they are grouped under one
incident (e.g. INCIDENT-EMAIL-001). Linked tickets skip individual troubleshooting, so no
further LLM calls or duplicate IT work happen for them; IT resolves the incident once and the
resolution fans out to every linked ticket.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state_machine import AgentState, can_transition
from app.core.config import get_settings
from app.core.logging import get_logger
from app.database import utcnow
from app.models.agent import AgentRun, Incident
from app.models.conversation import Conversation
from app.models.ticket import SolutionConfidence, Ticket, TicketStatus
from app.models.user import User
from app.rag.retriever import TicketHit, similar_tickets
from app.services import knowledge, tickets as ticket_svc
from app.services.classification import INTENT_LABELS
from app.services.priority import LEVELS, RANK
from app.vector_store.manager import ticket_text

logger = get_logger(__name__)
settings = get_settings()

# Tickets still inside the automated flow; these are switched to LINKED_INCIDENT when grouped
IN_AI_FLOW = (TicketStatus.NEW, TicketStatus.AI_ANALYSIS, TicketStatus.TROUBLESHOOTING,
              TicketStatus.AWAITING_USER, TicketStatus.AWAITING_APPROVAL)


def as_aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC so comparisons work on both databases."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def find_user_duplicate(db: AsyncSession, ticket: Ticket) -> Optional[TicketHit]:
    """Same user already has an open ticket about the same issue."""
    hits = await similar_tickets(db, ticket_text(ticket), category_id=ticket.category_id,
                                 exclude_ticket_id=ticket.id,
                                 min_similarity=settings.DUPLICATE_SIMILARITY_THRESHOLD,
                                 statuses=tuple(s for s in TicketStatus.OPEN),
                                 cross_category_min=settings.CROSS_CATEGORY_SIMILARITY)
    cutoff = utcnow() - timedelta(days=14)
    for h in hits:
        if h.ticket.user_id == ticket.user_id and as_aware(h.ticket.created_at) >= cutoff \
                and h.ticket.duplicate_of_id is None:
            return h
    return None


async def mark_duplicate(db: AsyncSession, ticket: Ticket, original: Ticket, similarity: float) -> None:
    ticket.duplicate_of_id = original.id
    ticket.extra_data = {**(ticket.extra_data or {}), "duplicate_similarity": round(similarity, 3)}
    await ticket_svc.set_status(db, ticket, TicketStatus.DUPLICATE,
                                description=f"Duplicate of {original.ticket_number} (similarity {similarity:.2f})")
    await ticket_svc.add_event(db, original, "duplicate_linked", new_value=ticket.ticket_number,
                               description=f"{ticket.ticket_number} was reported again by the same user")


@dataclass
class CorrelationResult:
    incident: Optional[Incident] = None
    created: bool = False
    similar_recent_count: int = 0          # other users reporting the same thing in the window
    linked_ticket_numbers: list[str] = field(default_factory=list)


async def correlate(db: AsyncSession, ticket: Ticket) -> CorrelationResult:
    window_start = utcnow() - timedelta(minutes=settings.INCIDENT_WINDOW_MINUTES)
    hits = await similar_tickets(db, ticket_text(ticket), category_id=ticket.category_id,
                                 exclude_ticket_id=ticket.id,
                                 min_similarity=settings.INCIDENT_SIMILARITY_THRESHOLD, k=50,
                                 cross_category_min=settings.CROSS_CATEGORY_SIMILARITY)
    others = [h for h in hits if h.ticket.user_id != ticket.user_id and h.ticket.status != TicketStatus.DUPLICATE]
    result = CorrelationResult()

    # 1) join an active incident that already contains a similar ticket
    for h in others:
        inc_id = h.ticket.incident_id
        if inc_id is None:
            continue
        inc = await db.get(Incident, inc_id)
        if inc and inc.status in ("active", "investigating"):
            await _link(db, inc, ticket, h.similarity, is_current=True)
            inc.last_reported = utcnow()
            result.incident = inc
            result.similar_recent_count = await _count_links(db, inc) - 1
            logger.info("incident_joined", incident=inc.incident_number, ticket_id=ticket.id,
                        similarity=round(h.similarity, 3))
            return result

    # 2) create a new incident when enough distinct users reported it recently
    recent = [h for h in others if as_aware(h.ticket.created_at) >= window_start
              and h.ticket.status in TicketStatus.OPEN]
    distinct_users = {h.ticket.user_id for h in recent}
    result.similar_recent_count = len(distinct_users)
    if len(distinct_users) + 1 < settings.INCIDENT_MIN_TICKETS:
        return result

    # keep one ticket per user (the most similar) as incident members
    members: dict[int, TicketHit] = {}
    for h in recent:
        if h.ticket.user_id not in members or h.similarity > members[h.ticket.user_id].similarity:
            members[h.ticket.user_id] = h

    inc = await _create_incident(db, ticket, list(members.values()))
    await _link(db, inc, ticket, 1.0, is_current=True)
    for h in members.values():
        await _link(db, inc, h.ticket, h.similarity)
        result.linked_ticket_numbers.append(h.ticket.ticket_number)
    result.incident, result.created = inc, True
    logger.info("incident_created", incident=inc.incident_number, tickets=len(members) + 1,
                category=ticket.category_name)
    return result


async def _create_incident(db: AsyncSession, ticket: Ticket, members: list[TicketHit]) -> Incident:
    cat = (ticket.category_name or "GENERAL").upper()
    count = (await db.execute(select(func.count(Incident.id)).where(
        Incident.incident_number.like(f"INCIDENT-{cat}-%")))).scalar() or 0
    all_tickets = [ticket] + [m.ticket for m in members]
    top_priority = max((t.priority or "medium" for t in all_tickets), key=lambda p: RANK.get(p, 1))
    priority = LEVELS[max(RANK.get(top_priority, 1), RANK["high"])]  # multi-user impact is at least HIGH
    label = INTENT_LABELS.get(ticket.intent or "", ticket.title)
    inc = Incident(
        incident_number=f"INCIDENT-{cat}-{count + 1:03d}",
        title=f"{label} - multiple users affected",
        description=(f"Automatically correlated: {len(all_tickets)} employees reported semantically similar "
                     f"{ticket.category_name} issues within {settings.INCIDENT_WINDOW_MINUTES} minutes."),
        category_id=ticket.category_id, priority=priority, status="active",
        department_id=ticket.category.department_id if ticket.category else None,
        detection_similarity=round(sum(m.similarity for m in members) / max(1, len(members)), 3),
        first_reported=min(as_aware(t.created_at) for t in all_tickets), last_reported=utcnow(),
    )
    db.add(inc)
    await db.flush()
    return inc


async def _link(db: AsyncSession, inc: Incident, t: Ticket, similarity: float, *, is_current: bool = False) -> None:
    """Attach a ticket to an incident. `is_current` marks the ticket whose own agent run is doing
    the correlation: that run finishes itself, so it is neither stopped nor messaged here."""
    if t.incident_id == inc.id:
        return
    t.incident_id = inc.id
    t.department_id = t.department_id or inc.department_id
    await ticket_svc.add_event(db, t, "linked_to_incident", new_value=inc.incident_number,
                               description=f"Correlated with {inc.incident_number} (similarity {similarity:.2f})")
    if t.status in IN_AI_FLOW:
        await ticket_svc.set_status(db, t, TicketStatus.LINKED_INCIDENT,
                                    description=f"Handled as part of {inc.incident_number}")
        if is_current:
            return
        # stop in-flight troubleshooting for this ticket: the incident owns it now
        runs = (await db.execute(select(AgentRun).where(AgentRun.ticket_id == t.id,
                                                        AgentRun.completed_at.is_(None)))).scalars().all()
        for run in runs:
            if can_transition(run.state, AgentState.LINKED_INCIDENT):
                ctx = dict(run.context or {})
                ctx.setdefault("state_history", []).append({"state": "linked_incident", "at": utcnow().isoformat()})
                run.context = ctx
                run.state, run.resolution_status, run.completed_at = "linked_incident", "linked_incident", utcnow()
        await ticket_svc.add_message(
            db, role="system", ticket_id=t.id, conversation_id=await _conversation_id(db, t),
            content=(f"Your report is part of a wider issue ({inc.incident_number}) that IT is already working on. "
                     f"You don't need to troubleshoot further - we'll update this ticket when it's fixed."),
            payload={"alerts": [{"type": "incident", "message": f"Linked to {inc.incident_number}"}],
                     "incident": {"number": inc.incident_number, "title": inc.title}},
        )


async def link_ticket(db: AsyncSession, inc: Incident, t: Ticket, similarity: float) -> None:
    """Manually link a ticket to an incident (IT support action)."""
    await _link(db, inc, t, similarity)
    inc.last_reported = utcnow()


async def _conversation_id(db: AsyncSession, t: Ticket) -> Optional[int]:
    return (await db.execute(select(Conversation.id).where(Conversation.ticket_id == t.id))).scalar()


async def _count_links(db: AsyncSession, inc: Incident) -> int:
    return (await db.execute(select(func.count(Ticket.id)).where(Ticket.incident_id == inc.id))).scalar() or 0


async def resolve_incident(db: AsyncSession, inc: Incident, *, resolution: str, root_cause: Optional[str],
                           user: User) -> int:
    """Resolve an incident and fan the resolution out to every linked open ticket.
    The resolution is captured as HUMAN_VERIFIED knowledge for future reports."""
    inc.status, inc.resolution, inc.root_cause, inc.resolved_at = "resolved", resolution, root_cause, utcnow()
    linked = (await db.execute(select(Ticket).where(Ticket.incident_id == inc.id))).unique().scalars().all()
    closed = 0
    for t in linked:
        if t.status in TicketStatus.OPEN:
            t.resolution_summary = f"Resolved with {inc.incident_number}: {resolution}"
            await ticket_svc.set_status(db, t, TicketStatus.RESOLVED, user_id=user.id,
                                        description=f"Resolved via {inc.incident_number}")
            await ticket_svc.add_message(db, role="agent", ticket_id=t.id, user_id=user.id,
                                         conversation_id=await _conversation_id(db, t),
                                         content=f"{inc.incident_number} has been resolved: {resolution}")
            closed += 1
    if linked:
        head = min(linked, key=lambda x: x.id)
        sol = await knowledge.create_solution(
            db, title=inc.title, problem=inc.description or inc.title, solution=resolution,
            steps=knowledge.steps_from_text(resolution), category_id=inc.category_id, intent=head.intent,
            confidence_level=SolutionConfidence.HUMAN_VERIFIED, source="it_support", ticket_id=head.id,
            root_cause=root_cause, created_by=user.id, verified_by=user.id,
        )
        logger.info("incident_resolved", incident=inc.incident_number, tickets_closed=closed, solution_id=sol.id)
    return closed
