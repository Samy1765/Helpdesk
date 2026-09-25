"""
Precision AI - Autonomous troubleshooting agent.

A persistent state machine (see state_machine.py) driven by chat events. Each ticket gets an
AgentRun whose `state` and `context` are stored in the database, so a run can be resumed by any
worker at any time. The agent implements the cost-optimised routing pipeline:

  LEVEL 0  deterministic policy (security / outage / physical damage / critical -> humans)
  LEVEL 1  keyword + intent classification           (done at intake)
  LEVEL 2  embedding similarity (duplicates, incidents, history)
  LEVEL 3  verified-solution / documented-procedure retrieval   -> no LLM call
  LEVEL 4  small/local LLM, grounded in retrieved context
  LEVEL 5  capable LLM, only on retries or low-confidence cases

It never exposes chain-of-thought: users see a progress checklist and an execution log, and the
escalation package carries a concise decision summary.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state_machine import PROGRESS_STEPS, TERMINAL, AgentState, assert_transition
from app.core.config import get_settings
from app.core.logging import get_logger
from app.database import utcnow
from app.llm import router as llm
from app.models.agent import AgentAction, AgentRun, Incident, LLMUsageLog
from app.models.ticket import SolutionConfidence, Ticket, TicketFeedback, TicketSolution, TicketStatus
from app.models.user import User
from app.rag import generator
from app.rag.generator import Candidate
from app.rag.retriever import Retrieval, retrieve
from app.services import correlation, escalation, knowledge, tickets as ticket_svc
from app.tools.executor import action_view, run_tool
from app.tools.registry import RESTRICTED, diagnostics_for, get_tool
from app.vector_store.manager import ticket_text

logger = get_logger(__name__)
settings = get_settings()
S = AgentState

HUMAN_ONLY_INTENTS = {"malware_suspected", "unauthorized_access", "server_outage", "database_outage"}
PHYSICAL_DAMAGE = r"\b(crack(ed)?|smashed|broken (screen|hinge|keyboard)|liquid|spill(ed)?|coffee|water damage|smoke|burning smell|swollen|bulging)\b"


@dataclass
class AgentOutcome:
    state: str
    message: str
    payload: dict = field(default_factory=dict)
    quick_replies: list[str] = field(default_factory=list)
    conversation_done: bool = False


# ---------------------------------------------------------------- helpers
def _ctx(run: AgentRun) -> dict:
    return dict(run.context or {})


def _save(run: AgentRun, ctx: dict) -> None:
    run.context = ctx  # reassign so the JSON column is flagged dirty


def _move(run: AgentRun, target: AgentState) -> None:
    assert_transition(run.state, target)
    ctx = _ctx(run)
    ctx.setdefault("state_history", []).append({"state": target.value, "at": utcnow().isoformat()})
    _save(run, ctx)
    run.state = target.value


def _progress(run: AgentRun, key: str, status: str) -> None:
    ctx = _ctx(run)
    ctx.setdefault("progress", {})[key] = status
    _save(run, ctx)


def _decide(run: AgentRun, note: str) -> None:
    """Append to the concise decision log (evidence + action, no internal deliberation)."""
    ctx = _ctx(run)
    ctx.setdefault("decisions", []).append(note)
    _save(run, ctx)
    run.reasoning_summary = " | ".join(ctx["decisions"][-8:])


def progress_view(run: Optional[AgentRun]) -> list[dict]:
    status = (run.context or {}).get("progress", {}) if run else {}
    return [{"key": k, "label": label, "status": status.get(k, "pending")} for k, label in PROGRESS_STEPS]


async def active_run(db: AsyncSession, ticket_id: int) -> Optional[AgentRun]:
    return (await db.execute(select(AgentRun).where(AgentRun.ticket_id == ticket_id)
                             .order_by(AgentRun.id.desc()).limit(1))).scalar_one_or_none()


def ticket_card(ticket: Ticket) -> dict:
    return {
        "id": ticket.id, "number": ticket.ticket_number, "title": ticket.title, "status": ticket.status,
        "category": ticket.category_name, "intent": ticket.intent, "sub_category": ticket.sub_category,
        "priority": ticket.priority, "user_priority": ticket.user_priority,
        "system_priority": ticket.system_priority, "confidence": ticket.ai_confidence,
        "department": ticket.department.name if ticket.department else None,
    }


async def _finish(db: AsyncSession, run: AgentRun, state: AgentState, resolution: str) -> None:
    _move(run, state)
    run.resolution_status = resolution
    now = utcnow()
    run.completed_at = now
    started = run.started_at if run.started_at.tzinfo else run.started_at.replace(tzinfo=now.tzinfo)
    run.latency_ms = round((now - started).total_seconds() * 1000, 1)
    await _sync_usage(db, run)


def _tool_label(name: str) -> str:
    spec = get_tool(name)
    return spec.label if spec else name


async def _sync_usage(db: AsyncSession, run: AgentRun) -> None:
    await db.flush()
    row = (await db.execute(select(
        func.count(LLMUsageLog.id), func.coalesce(func.sum(LLMUsageLog.prompt_tokens + LLMUsageLog.completion_tokens), 0),
        func.coalesce(func.sum(LLMUsageLog.estimated_cost), 0.0),
    ).where(LLMUsageLog.agent_run_id == run.id, LLMUsageLog.success.is_(True)))).one()
    run.llm_calls, run.tokens_used, run.estimated_cost = int(row[0]), int(row[1]), float(row[2])


# ---------------------------------------------------------------- entry point
async def start(db: AsyncSession, ticket: Ticket, user: User, *, intake: dict,
                client_env: Optional[dict] = None) -> AgentOutcome:
    """Run the agent from NEW until it needs the user (VERIFY) or reaches a terminal state."""
    t0 = time.perf_counter()
    run = AgentRun(ticket_id=ticket.id, state=S.NEW.value, context={"client_env": client_env or {}})
    db.add(run)
    await db.flush()
    alerts: list[dict] = list(intake.get("alerts", []))
    payload: dict = {}

    # UNDERSTAND + CLASSIFY were computed during intake; record them as evidence
    _move(run, S.UNDERSTAND)
    _progress(run, "understand", "done")
    await ticket_svc.add_step(db, ticket, step_key="understand", title="Ticket ingestion",
                              detail=f"Created from AI chat conversation ({len(ticket.description)} chars collected)",
                              agent_run_id=run.id)
    _move(run, S.CLASSIFY)
    _progress(run, "classify", "done")
    _progress(run, "priority", "done")
    cls = intake.get("classification", {})
    await ticket_svc.add_step(
        db, ticket, step_key="classify", title="Pattern classification",
        detail=(f"{ticket.category_name} / {ticket.sub_category or ticket.intent or 'general'} "
                f"({(ticket.ai_confidence or 0) * 100:.0f}% confidence, {cls.get('method', 'rules')}); "
                f"priority {ticket.priority.upper()}"
                + (f" (user selected {ticket.user_priority.upper()})" if ticket.user_priority else "")),
        agent_run_id=run.id)
    _decide(run, f"Classified as {ticket.category_name}/{ticket.intent} via {cls.get('method', 'rules')}")
    run.routing_level = "L1_rules" if cls.get("method") in ("rules", "default") else "L4_small_llm"

    # CHECK_DUPLICATE (LEVEL 2): same-user duplicate, then cross-user incident correlation
    _move(run, S.CHECK_DUPLICATE)
    dup = await correlation.find_user_duplicate(db, ticket)
    if dup is not None:
        await correlation.mark_duplicate(db, ticket, dup.ticket, dup.similarity)
        _progress(run, "duplicates", "done")
        _decide(run, f"Same-user duplicate of {dup.ticket.ticket_number} ({dup.similarity:.2f})")
        await ticket_svc.add_step(db, ticket, step_key="check_duplicate", title="Duplicate detected",
                                  detail=f"Matches your open ticket {dup.ticket.ticket_number} "
                                         f"({dup.similarity * 100:.0f}% similar)", agent_run_id=run.id)
        run.routing_level = "L2_similarity"
        await _finish(db, run, S.DUPLICATE, "duplicate")
        payload["duplicate"] = {"number": dup.ticket.ticket_number, "title": dup.ticket.title,
                                "status": dup.ticket.status, "similarity": round(dup.similarity, 3)}
        alerts.append({"type": "duplicate", "message": f"Similar ticket found: you already reported this as "
                                                       f"{dup.ticket.ticket_number}."})
        return _outcome(run, ticket, alerts, payload, conversation_done=True, message=(
            f"It looks like you already reported this issue in **{dup.ticket.ticket_number}** "
            f"(\"{dup.ticket.title}\", currently {dup.ticket.status.replace('_', ' ')}). I've linked this "
            f"report to it instead of opening a second ticket, so nobody works on it twice."))

    corr = await correlation.correlate(db, ticket)
    _progress(run, "duplicates", "done")
    if corr.incident is not None:
        inc = corr.incident
        _decide(run, f"Correlated into {inc.incident_number}")
        await ticket_svc.add_step(db, ticket, step_key="check_duplicate", title="Incident correlation",
                                  detail=f"Linked to {inc.incident_number}: {inc.title}", agent_run_id=run.id)
        run.routing_level = "L2_similarity"
        await db.refresh(ticket)
        await _finish(db, run, S.LINKED_INCIDENT, "linked_incident")
        payload["incident"] = {"number": inc.incident_number, "title": inc.title, "status": inc.status,
                               "created": corr.created, "reports": corr.similar_recent_count + 1}
        alerts.append({"type": "incident", "message": (
            f"{corr.similar_recent_count + 1} employees reported a similar {ticket.category_name} issue in the last "
            f"{settings.INCIDENT_WINDOW_MINUTES} minutes. This appears to be part of {inc.incident_number}.")})
        return _outcome(run, ticket, alerts, payload, conversation_done=True, message=(
            f"This issue appears to be part of an existing incident, **{inc.incident_number}** - "
            f"{inc.title}. The {inc.department.name if inc.department else 'IT'} team is working on it, "
            f"so there's no need for individual troubleshooting. Your ticket **{ticket.ticket_number}** is "
            f"linked and will be resolved automatically when the incident is fixed."))
    if corr.similar_recent_count:
        alerts.append({"type": "info", "message": (
            f"{corr.similar_recent_count} other employee(s) reported a similar {ticket.category_name} issue in the "
            f"last {settings.INCIDENT_WINDOW_MINUTES} minutes. IT is being notified if more reports arrive.")})
    await ticket_svc.add_step(db, ticket, step_key="check_duplicate", title="Duplicate & incident check",
                              detail="No duplicate or active incident found"
                                     + (f"; {corr.similar_recent_count} similar recent report(s)"
                                        if corr.similar_recent_count else ""), agent_run_id=run.id)

    # SEARCH_HISTORY (LEVEL 2/3)
    _move(run, S.SEARCH_HISTORY)
    retrieval = await retrieve(db, ticket_text(ticket), category_id=ticket.category_id, intent=ticket.intent,
                               exclude_ticket_id=ticket.id)
    run.retrieval_hits = retrieval.hit_count
    ctx = _ctx(run)
    ctx["retrieval"] = retrieval.summary()
    _save(run, ctx)
    _progress(run, "knowledge", "done")
    payload["similar"] = [{"number": h.ticket.ticket_number, "title": h.ticket.title, "status": h.ticket.status,
                           "similarity": round(h.similarity, 3)} for h in retrieval.similar_tickets[:3]]
    best = retrieval.solutions[0] if retrieval.solutions else None
    await ticket_svc.add_step(
        db, ticket, step_key="search_history", title="Vector similarity search",
        detail=(f"{len(retrieval.solutions)} known solution(s), {len(retrieval.chunks)} KB section(s), "
                f"{len(retrieval.similar_tickets)} similar ticket(s)"
                + (f"; best match {best.source_ticket_number or 'SOL-' + str(best.solution.id)} "
                   f"({best.similarity * 100:.0f}%)" if best else "")),
        agent_run_id=run.id)
    _decide(run, f"Retrieved {retrieval.hit_count} knowledge hit(s)")
    if best and best.source_ticket_number:
        alerts.append({"type": "info", "message": f"Similar incident detected: {best.source_ticket_number} "
                                                  f"({best.similarity * 100:.0f}% similar)."})

    # PLAN (LEVEL 0 policy first)
    _move(run, S.PLAN)
    policy_reason = _policy_escalation(ticket)
    if policy_reason:
        interim = generator.from_chunk(retrieval.chunks[0]) if retrieval.chunks else None
        _decide(run, f"Policy: {policy_reason}")
        run.routing_level = "L0_policy"
        return await _escalate(db, run, ticket, policy_reason, alerts, payload, interim=interim)

    # TROUBLESHOOT: safe automated diagnostics
    _move(run, S.TROUBLESHOOT)
    _progress(run, "troubleshoot", "running")
    evidence = await _run_diagnostics(db, run, ticket)
    down = [e for e in evidence if e.get("ok") is False and e["tool"] == "service_status"]
    if down:
        reason = f"Automated check shows a service problem: {down[0]['summary']}"
        _decide(run, reason)
        return await _escalate(db, run, ticket, reason, alerts, payload)

    candidate = await _next_candidate(db, run, ticket, retrieval)
    if candidate is None:
        return await _escalate(db, run, ticket, "No verified solution or safe suggestion available", alerts, payload)
    out = await _present(db, run, ticket, candidate, alerts, payload)
    logger.info("agent_run_awaiting_user", ticket_id=ticket.id, agent_run_id=run.id,
                routing_level=run.routing_level, latency_ms=round((time.perf_counter() - t0) * 1000, 1))
    return out


# ---------------------------------------------------------------- policy
def _policy_escalation(ticket: Ticket) -> Optional[str]:
    text = f"{ticket.title} {ticket.description}".lower()
    if ticket.category_name == "Security" and ticket.intent != "phishing_report":
        return "Security incidents are always handled by the Security team"
    if ticket.intent == "phishing_report" and re.search(r"clicked|entered (my )?(password|credentials)|opened the attachment", text):
        return "Possible credential compromise after phishing - Security must investigate"
    if ticket.intent in HUMAN_ONLY_INTENTS:
        return "Shared infrastructure outage - requires the owning operations team"
    if ticket.category_name == "Hardware" and re.search(PHYSICAL_DAMAGE, text):
        return "Physical damage requires hands-on hardware support"
    if ticket.priority == "critical":
        return "CRITICAL priority tickets are routed to humans immediately"
    return None


# ---------------------------------------------------------------- diagnostics
async def _run_diagnostics(db: AsyncSession, run: AgentRun, ticket: Ticket) -> list[dict]:
    evidence: list[dict] = []
    checks = diagnostics_for(ticket.category_name)
    client_env = (run.context or {}).get("client_env") or {}
    if client_env:
        checks.append(("client_environment", {"client": client_env}))
    for tool_name, params in checks:
        action = await run_tool(db, run, ticket, tool_name, params)
        res = action.result or {}
        evidence.append({"tool": tool_name, "ok": res.get("ok"), "summary": res.get("summary", ""),
                         "status": action.status})
        if action.status in ("executed", "failed"):
            await ticket_svc.add_step(db, ticket, step_key="troubleshoot", title=f"Probe: {_tool_label(tool_name)}",
                                      detail=res.get("summary", ""), status="completed" if res.get("ok") else "failed",
                                      agent_run_id=run.id)
    ctx = _ctx(run)
    ctx["evidence"] = evidence
    _save(run, ctx)
    return evidence


# ---------------------------------------------------------------- candidate selection
async def _next_candidate(db: AsyncSession, run: AgentRun, ticket: Ticket, retrieval: Retrieval) -> Optional[Candidate]:
    ctx = _ctx(run)
    tried = ctx.get("tried", [])
    tried_solutions = {c.get("solution_id") for c in tried if c.get("solution_id")}
    tried_sources = {s for c in tried for s in c.get("sources", [])}
    tried_kinds = [c.get("kind") for c in tried]
    previous = [Candidate(**c) for c in tried]
    tiers = await llm.available_tiers()
    llm_available = any(tiers.values())

    # LEVEL 3: verified / proven solution -> reuse directly, no LLM call
    for hit in retrieval.solutions:
        if hit.solution.id not in tried_solutions and hit.reusable_without_llm:
            _decide(run, f"Reusing {hit.solution.confidence_level} solution SOL-{hit.solution.id} "
                         f"({hit.similarity:.2f}) without LLM")
            run.routing_level = "L3_verified_retrieval"
            _mark_llm_skipped(run)
            return generator.from_solution(hit, "L3_verified_retrieval")

    # LEVEL 4/5: grounded generation. Large model on retries or when classification was uncertain.
    if llm_available and tried_kinds.count("ai_grounded") + tried_kinds.count("ai_generated") < 2:
        use_large = run.attempt >= 1 or (ticket.ai_confidence or 0) < 0.6
        tier = llm.LARGE if use_large else llm.SMALL
        evidence = ctx.get("evidence", [])
        cand = await generator.generate(db, ticket, retrieval, previous=previous, evidence=evidence,
                                        tier=tier, run_id=run.id)
        if cand is not None and not (cand.kind == "ai_generated" and ticket.category_name == "Security"):
            run.routing_level = cand.routing_level
            run.model_used = cand.model
            _decide(run, f"Generated {cand.kind} suggestion with {cand.model}")
            return cand

    # Remaining retrieved knowledge (no LLM available, or generation declined)
    for hit in retrieval.solutions:
        if hit.solution.id not in tried_solutions:
            _decide(run, f"Presenting {hit.solution.confidence_level} solution SOL-{hit.solution.id}")
            run.routing_level = run.routing_level if llm_available else "L3_verified_retrieval"
            if not llm_available:
                _mark_llm_skipped(run)
            return generator.from_solution(hit, "L3_verified_retrieval")
    for hit in retrieval.chunks:
        if hit.ref not in tried_sources:
            _decide(run, f"Presenting documented procedure {hit.ref}")
            if not llm_available:
                run.routing_level = "L3_verified_retrieval"
                _mark_llm_skipped(run)
            return generator.from_chunk(hit)
    return None


def _mark_llm_skipped(run: AgentRun) -> None:
    ctx = _ctx(run)
    ctx["llm_skipped"] = True
    _save(run, ctx)


# ---------------------------------------------------------------- present / verify
async def _present(db: AsyncSession, run: AgentRun, ticket: Ticket, cand: Candidate, alerts: list[dict],
                   payload: dict) -> AgentOutcome:
    ctx = _ctx(run)
    ctx["current"] = cand.as_dict()
    _save(run, ctx)
    run.confidence = cand.confidence

    approvals = []
    for tool_name in cand.automated_actions:
        spec = get_tool(tool_name)
        if spec is None or spec.permission != RESTRICTED:
            continue  # the agent never proposes dangerous actions on its own
        action = await run_tool(db, run, ticket, tool_name, {"application": ticket.entities.get("application", "")}
                                if "application" in spec.params else {})
        approvals.append(action_view(action))
    if approvals:
        alerts.append({"type": "approval", "message": "Human approval required before executing this action."})

    label = cand.label
    if cand.kind == "solution" and cand.label in ("VERIFIED SOLUTION", "HUMAN-APPROVED SOLUTION"):
        alerts.append({"type": "success", "message": "Known verified solution found."})
    await ticket_svc.add_step(
        db, ticket, step_key="troubleshoot",
        title=f"Remediation {'retrieved' if cand.kind in ('solution', 'kb_procedure') else 'generated'}",
        detail=f"{label}: {cand.title} ({', '.join(cand.sources) or cand.model or 'n/a'})", agent_run_id=run.id)
    await ticket_svc.add_step(db, ticket, step_key="verify", title="Verification",
                              detail="Waiting for the employee to confirm whether the fix worked",
                              status="running", performed_by="user", agent_run_id=run.id)
    _move(run, S.VERIFY)
    _progress(run, "troubleshoot", "done")
    _progress(run, "verify", "running")
    await ticket_svc.set_status(db, ticket, TicketStatus.AWAITING_USER, description="Solution proposed")
    await _sync_usage(db, run)

    payload["solution"] = cand.as_dict()
    payload["approvals"] = approvals
    source = (f" from **{cand.source_ticket}**" if cand.source_ticket else "")
    intro = {
        "solution": f"I found a **{label.lower()}**{source} that matches your issue "
                    f"({(cand.similarity or cand.confidence) * 100:.0f}% match).",
        "kb_procedure": "I found the documented procedure for this in the IT knowledge base.",
        "ai_grounded": "Based on our IT documentation, here is a suggested fix (AI-generated, grounded in "
                       f"{', '.join(cand.sources)}).",
        "ai_generated": "No documented fix matched, so here is an AI-generated suggestion with low-risk checks. "
                        "If it doesn't help, I'll hand this to a specialist.",
    }[cand.kind]
    attempt_note = "Let's try a different approach. " if run.attempt else ""
    return _outcome(run, ticket, alerts, payload, quick_replies=["Yes, it's fixed", "No, still not working"],
                    message=f"{attempt_note}{intro} Please try the steps below, then let me know: "
                            f"**did this resolve your issue?**")


async def handle_feedback(db: AsyncSession, ticket: Ticket, user: User, resolved: bool,
                          comment: Optional[str] = None) -> AgentOutcome:
    run = await active_run(db, ticket.id)
    if run is None or run.state != S.VERIFY.value:
        raise ValueError("This ticket is not waiting for confirmation")
    ctx = _ctx(run)
    cand = Candidate(**ctx["current"])
    db.add(TicketFeedback(ticket_id=ticket.id, user_id=user.id, solution_id=cand.solution_id,
                          issue_resolved=resolved, comments=comment))
    sol = await db.get(TicketSolution, cand.solution_id) if cand.solution_id else None
    if sol is not None:
        await knowledge.record_outcome(db, sol, resolved)

    if resolved:
        return await _resolve(db, run, ticket, user, cand, sol)

    # not resolved -> RETRY with another candidate, or ESCALATE
    ctx = _ctx(run)
    ctx.setdefault("tried", []).append(cand.as_dict())
    ctx.pop("current", None)
    _save(run, ctx)
    run.attempt += 1
    _decide(run, f"Attempt {run.attempt} ({cand.label}) did not resolve the issue")
    await ticket_svc.add_step(db, ticket, step_key="verify", title="Verification failed",
                              detail=f"Employee reported that '{cand.title}' did not fix the issue"
                                     + (f": {comment}" if comment else ""), status="failed", performed_by="user",
                              agent_run_id=run.id)
    alerts: list[dict] = []
    payload: dict = {}
    if run.attempt >= settings.AGENT_MAX_ATTEMPTS:
        _move(run, S.ESCALATE)
        return await _escalate(db, run, ticket, f"Not resolved after {run.attempt} troubleshooting attempt(s)",
                               alerts, payload, already_moved=True)
    _move(run, S.RETRY)
    retrieval = await retrieve(db, ticket_text(ticket) + (f" {comment}" if comment else ""),
                               category_id=ticket.category_id, intent=ticket.intent, exclude_ticket_id=ticket.id)
    nxt = await _next_candidate(db, run, ticket, retrieval)
    if nxt is None:
        _move(run, S.ESCALATE)
        return await _escalate(db, run, ticket, "No alternative verified solution available", alerts, payload,
                               already_moved=True)
    _move(run, S.TROUBLESHOOT)
    return await _present(db, run, ticket, nxt, alerts, payload)


async def _resolve(db: AsyncSession, run: AgentRun, ticket: Ticket, user: User, cand: Candidate,
                   sol: Optional[TicketSolution]) -> AgentOutcome:
    ticket.resolved_by_ai = True
    ticket.resolution_summary = f"{cand.label}: {cand.title}"
    await ticket_svc.set_status(db, ticket, TicketStatus.RESOLVED, user_id=user.id,
                                description="Employee confirmed the AI-proposed fix worked")
    await ticket_svc.add_step(db, ticket, step_key="verify", title="Verification passed",
                              detail="Employee confirmed the issue is resolved", performed_by="user",
                              agent_run_id=run.id)
    # Self-improving loop: AI suggestions become USER_CONFIRMED knowledge candidates; existing
    # solutions keep their level (their success counter was already incremented).
    if sol is None:
        summary = f"{cand.title}: " + "; ".join(cand.steps) if cand.kind == "kb_procedure" else cand.summary
        new_sol = await knowledge.capture_resolution(
            db, ticket, solution_text=summary, steps=cand.steps, source="agent",
            confidence_level=SolutionConfidence.USER_CONFIRMED,
        )
        new_sol.times_used, new_sol.times_successful = 1, 1
        _decide(run, f"Captured resolution as SOL-{new_sol.id} (user_confirmed)")
    _progress(run, "verify", "done")
    _progress(run, "outcome", "done")
    await _finish(db, run, S.RESOLVED, "resolved")
    return _outcome(run, ticket, [{"type": "success", "message": "Ticket resolved by the AI agent."}], {},
                    conversation_done=True,
                    message=f"Great - I've marked **{ticket.ticket_number}** as resolved. The fix has been recorded "
                            f"so it can help colleagues with the same problem. Anything else I can help with?")


async def _escalate(db: AsyncSession, run: AgentRun, ticket: Ticket, reason: str, alerts: list[dict],
                    payload: dict, interim: Optional[Candidate] = None, already_moved: bool = False) -> AgentOutcome:
    if not already_moved:
        _move(run, S.ESCALATE)
    run.escalation_reason = reason
    progress = (run.context or {}).get("progress", {})
    if progress.get("troubleshoot") != "done":
        _progress(run, "troubleshoot", "skipped")
    # verification "ran" (and failed) if the user was already asked to confirm a fix
    _progress(run, "verify", "done" if progress.get("verify") == "running" else "skipped")
    esc = await escalation.escalate(db, ticket, reason=reason, run=run)
    await ticket_svc.add_step(db, ticket, step_key="escalate", title="Escalated to human support",
                              detail=f"{esc.department.name}: {reason}", agent_run_id=run.id)
    _progress(run, "outcome", "done")
    await _finish(db, run, S.ESCALATED, "escalated")
    await db.refresh(ticket)
    alerts.append({"type": "escalation",
                   "message": f"AI could not safely resolve this issue. Escalating to {esc.department.name}."})
    payload["escalation"] = {"department": esc.department.name, "reason": reason,
                             "assignee": ticket.assignee.full_name if ticket.assignee else None}
    if interim is not None:
        payload["solution"] = interim.as_dict()
    msg = (f"I've escalated **{ticket.ticket_number}** to the **{esc.department.name}** team"
           + (f" and assigned it to {ticket.assignee.full_name}" if ticket.assignee else "")
           + f". Reason: {reason}. They'll receive everything we've tried so far, so you won't have to repeat yourself.")
    if interim is not None:
        msg += " While you wait, please follow the interim guidance below."
    return _outcome(run, ticket, alerts, payload, conversation_done=True, message=msg)


def _outcome(run: AgentRun, ticket: Ticket, alerts: list[dict], payload: dict, *, message: str,
             quick_replies: Optional[list[str]] = None, conversation_done: bool = False) -> AgentOutcome:
    payload = {**payload, "alerts": alerts, "progress": progress_view(run), "ticket": ticket_card(ticket),
               "agent": {"state": run.state, "attempt": run.attempt, "routing_level": run.routing_level,
                         "run_id": run.id}}
    return AgentOutcome(state=run.state, message=message, payload=payload, quick_replies=quick_replies or [],
                        conversation_done=conversation_done)


async def close_runs_for_human(db: AsyncSession, ticket: Ticket, note: str) -> None:
    """A human took over (assign/resolve): stop the automated run."""
    run = await active_run(db, ticket.id)
    if run and run.state not in {s.value for s in TERMINAL}:
        _decide(run, note)
        _move(run, S.CLOSED)
        run.resolution_status = "human_takeover"
        run.completed_at = utcnow()
        await _sync_usage(db, run)


async def after_action_decision(db: AsyncSession, action: AgentAction) -> AgentOutcome:
    ticket = action.ticket
    run = await db.get(AgentRun, action.agent_run_id)
    if run is None:
        raise ValueError("Agent run not found")
    res = action.result or {}
    await ticket_svc.add_step(db, ticket, step_key="troubleshoot",
                              title=f"{'Executed' if action.status == 'approved' else 'Declined'}: "
                                    f"{_tool_label(action.tool_name)}",
                              detail=res.get("summary", ""), agent_run_id=action.agent_run_id)
    if action.status == "approved":
        msg = f"Done - {res.get('summary', 'the action was executed')}. Did that resolve the issue?"
    else:
        msg = "Understood, I won't run that action. You can still follow the manual steps. Did they resolve the issue?"
    return _outcome(run, ticket, [], {"approvals": [action_view(action)]}, message=msg,
                    quick_replies=["Yes, it's fixed", "No, still not working"] if run.state == S.VERIFY.value else [])


async def incident_for(db: AsyncSession, ticket: Ticket) -> Optional[Incident]:
    return await db.get(Incident, ticket.incident_id) if ticket.incident_id else None
