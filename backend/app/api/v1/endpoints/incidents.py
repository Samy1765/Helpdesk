"""
Precision AI - Incident Correlation Center.
Everyone can see active incidents (a status page); linked tickets and management are staff-only.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import incident_out, iso, ticket_out
from app.core.deps import STAFF_ROLES, get_current_user, is_staff, require_role
from app.database import get_db
from app.models.agent import Incident
from app.models.ticket import Ticket, TicketEvent
from app.models.user import User
from app.services import correlation, tickets as ticket_svc

router = APIRouter(prefix="/incidents", tags=["Incidents"])


class IncidentUpdate(BaseModel):
    status: Optional[Literal["active", "investigating"]] = None
    root_cause: Optional[str] = Field(default=None, max_length=2000)


class IncidentResolve(BaseModel):
    resolution: str = Field(min_length=5, max_length=4000)
    root_cause: Optional[str] = Field(default=None, max_length=2000)


class LinkIn(BaseModel):
    ticket_id: int


async def _counts(db: AsyncSession, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    rows = await db.execute(select(Ticket.incident_id, func.count(Ticket.id)).where(Ticket.incident_id.in_(ids))
                            .group_by(Ticket.incident_id))
    return {r[0]: int(r[1]) for r in rows.all()}


@router.get("")
async def list_incidents(state: Literal["active", "resolved", "all"] = "active", db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    q = select(Incident)
    if state == "active":
        q = q.where(Incident.status.in_(("active", "investigating")))
    elif state == "resolved":
        q = q.where(Incident.status == "resolved")
    rows = (await db.execute(q.order_by(Incident.last_reported.desc()).limit(100))).unique().scalars().all()
    counts = await _counts(db, [i.id for i in rows])
    return [incident_out(i, counts.get(i.id, 0)) for i in rows]


@router.get("/{incident_id}")
async def incident_detail(incident_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    inc = await db.get(Incident, incident_id)
    if inc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    tickets = (await db.execute(select(Ticket).where(Ticket.incident_id == inc.id)
                                .order_by(Ticket.created_at))).unique().scalars().all()
    events = (await db.execute(select(TicketEvent).where(TicketEvent.ticket_id.in_([t.id for t in tickets]),
                                                         TicketEvent.event_type.in_(("ticket_created", "linked_to_incident",
                                                                                     "status_changed")))
                               .order_by(TicketEvent.created_at.desc()).limit(40))).unique().scalars().all()
    staff = is_staff(user)
    mine = [t for t in tickets if t.user_id == user.id]
    departments = sorted({t.creator.department.name for t in tickets if t.creator and t.creator.department})
    return {
        "incident": incident_out(inc, len(tickets)),
        "affected_users": len({t.user_id for t in tickets}),
        "affected_departments": departments,
        "tickets": [ticket_out(t) for t in (tickets if staff else mine)],
        "timeline": [{"at": iso(e.created_at), "type": e.event_type, "description": e.description,
                      "ticket_id": e.ticket_id} for e in events] if staff else [],
        "can_manage": staff,
    }


@router.patch("/{incident_id}")
async def update_incident(incident_id: int, data: IncidentUpdate, db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_role(*STAFF_ROLES))):
    inc = await db.get(Incident, incident_id)
    if inc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(inc, field, value)
    await ticket_svc.audit(db, "incident_updated", user_id=user.id, resource_type="incident", resource_id=inc.id,
                           details=data.model_dump(exclude_unset=True))
    return incident_out(inc)


@router.post("/{incident_id}/resolve")
async def resolve_incident(incident_id: int, data: IncidentResolve, db: AsyncSession = Depends(get_db),
                           user: User = Depends(require_role(*STAFF_ROLES))):
    inc = await db.get(Incident, incident_id)
    if inc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    if inc.status == "resolved":
        raise HTTPException(status.HTTP_409_CONFLICT, "Incident already resolved")
    closed = await correlation.resolve_incident(db, inc, resolution=data.resolution, root_cause=data.root_cause,
                                                user=user)
    await ticket_svc.audit(db, "incident_resolved", user_id=user.id, resource_type="incident", resource_id=inc.id,
                           details={"tickets_closed": closed})
    return {"incident": incident_out(inc), "tickets_resolved": closed}


@router.post("/{incident_id}/link")
async def link_ticket(incident_id: int, data: LinkIn, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_role(*STAFF_ROLES))):
    inc = await db.get(Incident, incident_id)
    ticket = await ticket_svc.get_ticket(db, data.ticket_id)
    if inc is None or ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident or ticket not found")
    await correlation.link_ticket(db, inc, ticket, similarity=1.0)
    await db.refresh(ticket)
    return ticket_out(ticket)
