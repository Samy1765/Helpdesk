"""
Precision AI - Response serializers shared by the API routers.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import get_settings
from app.database import utcnow
from app.models.agent import Incident
from app.models.knowledge import KnowledgeDocument
from app.models.ticket import Ticket, TicketMessage, TicketSolution, TicketStatus
from app.models.user import User

settings = get_settings()


def iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def user_out(u: User) -> dict:
    return {
        "id": u.id, "email": u.email, "username": u.username, "full_name": u.full_name, "role": u.role_name,
        "department": u.department.name if u.department else None, "department_id": u.department_id,
        "job_title": u.job_title, "location": u.location, "is_active": u.is_active,
        "created_at": iso(u.created_at), "last_login_at": iso(u.last_login_at),
    }


def sla(ticket: Ticket) -> dict:
    target = settings.sla_minutes.get(ticket.priority or "medium", 480)
    created = ticket.created_at if ticket.created_at.tzinfo else ticket.created_at.replace(tzinfo=timezone.utc)
    end = ticket.resolved_at or utcnow()
    end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    elapsed = max(0.0, (end - created).total_seconds() / 60)
    return {
        "target_minutes": target, "elapsed_minutes": round(elapsed, 1),
        "remaining_minutes": round(target - elapsed, 1), "percent": round(min(100.0, elapsed / target * 100), 1),
        "breached": elapsed > target, "due_at": iso(created + timedelta(minutes=target)),
    }


def ticket_out(t: Ticket) -> dict:
    return {
        "id": t.id, "ticket_number": t.ticket_number, "title": t.title, "description": t.description,
        "category": t.category_name, "category_id": t.category_id, "sub_category": t.sub_category,
        "intent": t.intent, "entities": t.entities or {}, "ai_confidence": t.ai_confidence,
        "classification_method": t.classification_method,
        "priority": t.priority, "user_priority": t.user_priority, "system_priority": t.system_priority,
        "priority_confidence": t.priority_confidence, "priority_reason": t.priority_reason,
        "priority_impact": t.priority_impact, "priority_urgency": t.priority_urgency,
        "status": t.status, "source": t.source, "is_open": t.status in TicketStatus.OPEN,
        "creator": {"id": t.creator.id, "name": t.creator.full_name,
                    "department": t.creator.department.name if t.creator.department else None,
                    "job_title": t.creator.job_title} if t.creator else None,
        "assignee": {"id": t.assignee.id, "name": t.assignee.full_name} if t.assignee else None,
        "department": t.department.name if t.department else None,
        "incident_id": t.incident_id, "duplicate_of_id": t.duplicate_of_id,
        "resolved_by_ai": t.resolved_by_ai, "resolution_summary": t.resolution_summary,
        "created_at": iso(t.created_at), "updated_at": iso(t.updated_at), "resolved_at": iso(t.resolved_at),
        "sla": sla(t),
    }


def message_out(m: TicketMessage) -> dict:
    return {
        "id": m.id, "role": m.role, "content": m.content, "payload": m.payload or {}, "is_internal": m.is_internal,
        "author": m.author.full_name if m.author else None, "created_at": iso(m.created_at),
        "ticket_id": m.ticket_id,
    }


def solution_out(s: TicketSolution, ticket_number: Optional[str] = None) -> dict:
    return {
        "id": s.id, "title": s.title, "problem_description": s.problem_description, "symptoms": s.symptoms,
        "root_cause": s.root_cause, "solution_description": s.solution_description, "steps": s.steps or [],
        "automated_actions": s.automated_actions or [], "confidence_level": s.confidence_level,
        "source": s.source, "category": s.category.name if s.category else None, "category_id": s.category_id,
        "intent": s.intent, "times_used": s.times_used, "times_successful": s.times_successful,
        "times_failed": s.times_failed, "success_rate": s.success_rate, "is_active": s.is_active,
        "rejected": s.rejected, "ticket_id": s.ticket_id, "ticket_number": ticket_number,
        "created_at": iso(s.created_at), "verified_at": iso(s.verified_at),
    }


def incident_out(i: Incident, ticket_count: Optional[int] = None) -> dict:
    return {
        "id": i.id, "incident_number": i.incident_number, "title": i.title, "description": i.description,
        "category": i.category.name if i.category else None, "priority": i.priority, "status": i.status,
        "department": i.department.name if i.department else None, "root_cause": i.root_cause,
        "resolution": i.resolution, "detection_similarity": i.detection_similarity,
        "first_reported": iso(i.first_reported), "last_reported": iso(i.last_reported),
        "resolved_at": iso(i.resolved_at), "created_at": iso(i.created_at), "ticket_count": ticket_count,
    }


def document_out(d: KnowledgeDocument, include_content: bool = True) -> dict:
    out = {
        "id": d.id, "title": d.title, "doc_type": d.doc_type, "category": d.category.name if d.category else None,
        "category_id": d.category_id, "source": d.source, "trust_level": d.trust_level, "is_active": d.is_active,
        "created_at": iso(d.created_at), "updated_at": iso(d.updated_at),
        "excerpt": d.content[:220].replace("#", "").strip(),
    }
    if include_content:
        out["content"] = d.content
    return out
