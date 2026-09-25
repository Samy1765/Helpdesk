"""
Precision AI - Analytics. Every number is computed from database rows at request time;
nothing is hard-coded. Estimates (token/cost savings) are labelled as such with their basis.
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database import utcnow
from app.models.agent import AgentAction, AgentRun, Incident, LLMUsageLog
from app.models.knowledge import KnowledgeDocument
from app.models.ticket import (
    SolutionConfidence, Ticket, TicketCategory, TicketEscalation, TicketSolution, TicketStatus,
)
from app.services.classification import INTENT_LABELS

settings = get_settings()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _pct(num: float, den: float) -> float:
    return round(num / den * 100, 1) if den else 0.0


async def _count(db: AsyncSession, *where) -> int:
    return int((await db.execute(select(func.count(Ticket.id)).where(*where))).scalar() or 0)


async def _avg_resolution_hours(db: AsyncSession, since: Optional[datetime] = None) -> Optional[float]:
    q = select(Ticket.created_at, Ticket.resolved_at).where(Ticket.resolved_at.is_not(None),
                                                            Ticket.status == TicketStatus.RESOLVED)
    if since:
        q = q.where(Ticket.resolved_at >= since)
    rows = (await db.execute(q)).all()
    if not rows:
        return None
    hours = [(_aware(r[1]) - _aware(r[0])).total_seconds() / 3600 for r in rows]
    return round(sum(hours) / len(hours), 2)


async def _distribution(db: AsyncSession, column, *where, limit: Optional[int] = None) -> list[dict]:
    q = select(column, func.count(Ticket.id)).where(*where).group_by(column).order_by(func.count(Ticket.id).desc())
    if limit:
        q = q.limit(limit)
    return [{"name": r[0] or "unknown", "count": int(r[1])} for r in (await db.execute(q)).all()]


async def _category_distribution(db: AsyncSession, *where) -> list[dict]:
    q = (select(TicketCategory.name, func.count(Ticket.id)).join(Ticket, Ticket.category_id == TicketCategory.id)
         .where(*where).group_by(TicketCategory.name).order_by(func.count(Ticket.id).desc()))
    return [{"name": r[0], "count": int(r[1])} for r in (await db.execute(q)).all()]


async def support_overview(db: AsyncSession) -> dict:
    open_statuses = Ticket.status.in_(TicketStatus.OPEN)
    total = await _count(db)
    resolved = await _count(db, Ticket.status == TicketStatus.RESOLVED)
    ai_resolved = await _count(db, Ticket.resolved_by_ai.is_(True))
    escalated_total = int((await db.execute(select(func.count(func.distinct(TicketEscalation.ticket_id))))).scalar() or 0)
    ai_flow_total = await _count(db, Ticket.source == "ai_chatbot")
    week_ago = utcnow() - timedelta(days=7)
    frequent = await _distribution(db, Ticket.intent, Ticket.created_at >= week_ago, Ticket.intent.is_not(None), limit=6)
    for f in frequent:
        f["label"] = INTENT_LABELS.get(f["name"], f["name"])
    return {
        "new_tickets": await _count(db, Ticket.status.in_((TicketStatus.NEW, TicketStatus.AI_ANALYSIS))),
        "open_tickets": await _count(db, open_statuses),
        "awaiting_user": await _count(db, Ticket.status == TicketStatus.AWAITING_USER),
        "escalated_open": await _count(db, Ticket.status.in_((TicketStatus.ESCALATED, TicketStatus.ASSIGNED,
                                                               TicketStatus.IN_PROGRESS))),
        "critical_open": await _count(db, open_statuses, Ticket.priority == "critical"),
        "ai_resolved": ai_resolved,
        "resolved": resolved,
        "duplicates": await _count(db, Ticket.status == TicketStatus.DUPLICATE),
        "incident_linked": await _count(db, Ticket.incident_id.is_not(None)),
        "active_incidents": int((await db.execute(select(func.count(Incident.id)).where(
            Incident.status.in_(("active", "investigating"))))).scalar() or 0),
        "pending_approvals": int((await db.execute(select(func.count(AgentAction.id)).where(
            AgentAction.status == "pending_approval"))).scalar() or 0),
        "avg_resolution_hours": await _avg_resolution_hours(db),
        "ai_resolution_rate": _pct(ai_resolved, resolved),
        "human_escalation_rate": _pct(escalated_total, ai_flow_total),
        "total_tickets": total,
        "category_distribution": await _category_distribution(db, open_statuses),
        "priority_distribution": await _distribution(db, Ticket.priority, open_statuses),
        "frequent_issues": frequent,
    }


async def admin_analytics(db: AsyncSession, days: int = 30) -> dict:
    now = utcnow()
    since = now - timedelta(days=days)
    total = await _count(db)
    in_window = Ticket.created_at >= since

    # ---- tickets per day (bucketed in Python: portable across PostgreSQL and SQLite) ----
    created = [(_aware(r[0]), r[1]) for r in (await db.execute(
        select(Ticket.created_at, Ticket.resolved_by_ai).where(in_window))).all()]
    per_day: dict[str, dict] = {}
    for i in range(days):
        d = (since + timedelta(days=i + 1)).date().isoformat()
        per_day[d] = {"date": d, "tickets": 0, "ai_resolved": 0}
    for ts, by_ai in created:
        d = ts.date().isoformat()
        if d in per_day:
            per_day[d]["tickets"] += 1
            per_day[d]["ai_resolved"] += 1 if by_ai else 0

    resolved = await _count(db, Ticket.status == TicketStatus.RESOLVED)
    ai_resolved = await _count(db, Ticket.resolved_by_ai.is_(True))
    ai_flow_total = await _count(db, Ticket.source == "ai_chatbot")
    escalated = int((await db.execute(select(func.count(func.distinct(TicketEscalation.ticket_id))))).scalar() or 0)
    duplicates = await _count(db, Ticket.status == TicketStatus.DUPLICATE)
    incident_linked = await _count(db, Ticket.incident_id.is_not(None))
    incidents = int((await db.execute(select(func.count(Incident.id)))).scalar() or 0)

    # ---- agent runs ----
    runs = (await db.execute(select(AgentRun.resolution_status, AgentRun.retrieval_hits, AgentRun.llm_calls,
                                    AgentRun.routing_level, AgentRun.context, AgentRun.state)
                             .where(AgentRun.started_at >= since))).all()
    completed = [r for r in runs if r.resolution_status in ("resolved", "escalated")]
    agent_resolved = [r for r in completed if r.resolution_status == "resolved"]
    searched = [r for r in runs if r.resolution_status not in ("duplicate", "linked_incident")]
    retrieval_hit = [r for r in searched if (r.retrieval_hits or 0) > 0]
    no_llm_resolved = [r for r in agent_resolved if (r.llm_calls or 0) == 0]
    skipped_llm = [r for r in runs if (r.context or {}).get("llm_skipped")
                   or r.resolution_status in ("duplicate", "linked_incident")]
    routing = Counter(r.routing_level or "unknown" for r in runs)

    # ---- LLM usage ----
    usage = (await db.execute(select(
        func.count(LLMUsageLog.id),
        func.coalesce(func.sum(case((LLMUsageLog.success.is_(True), 1), else_=0)), 0),
        func.coalesce(func.sum(LLMUsageLog.prompt_tokens), 0),
        func.coalesce(func.sum(LLMUsageLog.completion_tokens), 0),
        func.coalesce(func.sum(LLMUsageLog.estimated_cost), 0.0),
        func.coalesce(func.sum(case((LLMUsageLog.cache_hit.is_(True), 1), else_=0)), 0),
    ).where(LLMUsageLog.created_at >= since))).one()
    by_purpose = [{"name": r[0] or "other", "calls": int(r[1]), "tokens": int(r[2] or 0)} for r in (await db.execute(
        select(LLMUsageLog.purpose, func.count(LLMUsageLog.id),
               func.sum(LLMUsageLog.prompt_tokens + LLMUsageLog.completion_tokens))
        .where(LLMUsageLog.created_at >= since).group_by(LLMUsageLog.purpose))).all()]
    by_provider = [{"name": f"{r[0]}:{r[1]}", "calls": int(r[2])} for r in (await db.execute(
        select(LLMUsageLog.provider, LLMUsageLog.model, func.count(LLMUsageLog.id))
        .where(LLMUsageLog.created_at >= since).group_by(LLMUsageLog.provider, LLMUsageLog.model))).all()]

    measured = (await db.execute(select(func.avg(LLMUsageLog.prompt_tokens + LLMUsageLog.completion_tokens)).where(
        LLMUsageLog.purpose == "troubleshooting", LLMUsageLog.success.is_(True),
        LLMUsageLog.cache_hit.is_(False)))).scalar()
    tokens_per_call = int(measured) if measured else settings.LLM_ESTIMATED_TOKENS_PER_CALL
    tokens_saved = len(skipped_llm) * tokens_per_call

    # ---- knowledge growth ----
    sol_rows = (await db.execute(select(TicketSolution.created_at, TicketSolution.confidence_level,
                                        TicketSolution.is_active))).all()
    doc_rows = (await db.execute(select(KnowledgeDocument.created_at))).all()
    growth: dict[str, int] = defaultdict(int)
    base = 0
    for ts, *_ in list(sol_rows) + list(doc_rows):
        ts = _aware(ts)
        if ts < since:
            base += 1
        else:
            growth[ts.date().isoformat()] += 1
    kb_growth, running = [], base
    for d in per_day:
        running += growth.get(d, 0)
        kb_growth.append({"date": d, "total": running})
    by_level = Counter(r[1] for r in sol_rows if r[2])

    top_intents = await _distribution(db, Ticket.intent, in_window, Ticket.intent.is_not(None), limit=8)
    for t in top_intents:
        t["label"] = INTENT_LABELS.get(t["name"], t["name"])

    return {
        "window_days": days,
        "overview": {
            "total_tickets": total,
            "tickets_in_window": len(created),
            "ai_resolution_percentage": _pct(ai_resolved, resolved),
            "human_escalation_percentage": _pct(escalated, ai_flow_total),
            "duplicates_prevented": duplicates + incident_linked,
            "duplicate_tickets": duplicates,
            "incident_linked_tickets": incident_linked,
            "incidents_detected": incidents,
            "avg_resolution_hours": await _avg_resolution_hours(db, since),
            "agent_success_rate": _pct(len(agent_resolved), len(completed)),
            "retrieval_hit_rate": _pct(len(retrieval_hit), len(searched)),
            "resolved_without_llm": len(no_llm_resolved),
            "knowledge_base_size": sum(by_level.values()) + len(doc_rows),
        },
        "tickets_per_day": list(per_day.values()),
        "category_distribution": await _category_distribution(db, in_window),
        "priority_distribution": await _distribution(db, Ticket.priority, in_window),
        "top_intents": top_intents,
        "routing_levels": [{"name": k, "count": v} for k, v in sorted(routing.items())],
        "knowledge_growth": kb_growth,
        "knowledge_by_level": [{"name": lvl, "count": by_level.get(lvl, 0)} for lvl in SolutionConfidence.ORDER],
        "llm_usage": {
            "calls": int(usage[0]), "successful_calls": int(usage[1]),
            "prompt_tokens": int(usage[2]), "completion_tokens": int(usage[3]),
            "total_tokens": int(usage[2]) + int(usage[3]), "estimated_cost_usd": round(float(usage[4]), 4),
            "cache_hits": int(usage[5]), "cache_hit_rate": _pct(int(usage[5]), int(usage[0])),
            "by_purpose": by_purpose, "by_provider": by_provider,
        },
        "savings": {
            "runs_without_llm": len(skipped_llm),
            "tokens_per_call": tokens_per_call,
            "estimate_basis": "measured" if measured else "configured (LLM_ESTIMATED_TOKENS_PER_CALL)",
            "estimated_tokens_saved": tokens_saved,
            "estimated_cost_saved_usd": round(tokens_saved / 1000 * settings.LLM_REFERENCE_COST_PER_1K, 4),
        },
    }
