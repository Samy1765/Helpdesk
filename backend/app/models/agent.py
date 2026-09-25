"""
Precision AI - Agent, Incident, LLM usage and audit models.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base, JSONType, utcnow

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.ticket import Ticket, TicketCategory


class AgentRun(Base):
    """
    One troubleshooting-agent run for a ticket. `state` is the current node of the agent
    state machine; `context` holds the serialisable working memory (candidate solutions,
    attempt counters, tool evidence) so a run survives process restarts.
    """
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    state: Mapped[str] = mapped_column(String(30), default="new", index=True)
    attempt: Mapped[int] = mapped_column(default=0)
    context: Mapped[dict] = mapped_column(JSONType, default=dict)
    routing_level: Mapped[Optional[str]] = mapped_column(String(40))  # deepest routing level reached
    model_used: Mapped[Optional[str]] = mapped_column(String(100))
    llm_calls: Mapped[int] = mapped_column(default=0)
    tokens_used: Mapped[int] = mapped_column(default=0)
    estimated_cost: Mapped[float] = mapped_column(default=0.0)
    retrieval_hits: Mapped[int] = mapped_column(default=0)
    confidence: Mapped[Optional[float]]
    resolution_status: Mapped[Optional[str]] = mapped_column(String(30))  # resolved | escalated | linked_incident | duplicate
    escalation_reason: Mapped[Optional[str]] = mapped_column(Text)
    reasoning_summary: Mapped[Optional[str]] = mapped_column(Text)  # concise decision log, not chain-of-thought
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[Optional[float]]

    ticket: Mapped["Ticket"] = relationship(back_populates="agent_runs")
    actions: Mapped[list["AgentAction"]] = relationship(back_populates="agent_run", order_by="AgentAction.id")


class AgentAction(Base):
    """Tool invocation requested by the agent, with permission level and approval state."""
    __tablename__ = "agent_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(80))
    permission_level: Mapped[str] = mapped_column(String(20))  # safe | restricted | dangerous
    parameters: Mapped[dict] = mapped_column(JSONType, default=dict)
    result: Mapped[Optional[dict]] = mapped_column(JSONType)
    # executed | failed | skipped | pending_approval | approved | rejected | blocked
    status: Mapped[str] = mapped_column(String(30), default="executed", index=True)
    approval_required: Mapped[bool] = mapped_column(default=False)
    approver_role: Mapped[Optional[str]] = mapped_column(String(30))  # requester | admin
    approved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[Optional[float]]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    agent_run: Mapped["AgentRun"] = relationship(back_populates="actions")
    ticket: Mapped["Ticket"] = relationship(lazy="joined")


class Incident(Base):
    """Correlated incident grouping many tickets that share a root cause."""
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ticket_categories.id"))
    priority: Mapped[Optional[str]] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)  # active | investigating | resolved
    department_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"))
    root_cause: Mapped[Optional[str]] = mapped_column(Text)
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    detection_similarity: Mapped[Optional[float]]
    first_reported: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_reported: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tickets: Mapped[list["Ticket"]] = relationship(back_populates="incident")
    department: Mapped[Optional["Department"]] = relationship(back_populates="incidents", lazy="joined")
    category: Mapped[Optional["TicketCategory"]] = relationship(lazy="joined")


class LLMUsageLog(Base):
    """Every LLM request (including cache hits) for cost monitoring."""
    __tablename__ = "llm_usage_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tickets.id"), index=True)
    agent_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("agent_runs.id"))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100))
    tier: Mapped[Optional[str]] = mapped_column(String(10))  # small | large
    purpose: Mapped[Optional[str]] = mapped_column(String(60))
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    estimated_cost: Mapped[float] = mapped_column(default=0.0)
    cache_hit: Mapped[bool] = mapped_column(default=False)
    success: Mapped[bool] = mapped_column(default=True)
    error: Mapped[Optional[str]] = mapped_column(String(300))
    latency_ms: Mapped[Optional[float]]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AuditLog(Base):
    """System-wide audit trail (auth, admin, approvals). Never stores secrets."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80), index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(60))
    resource_id: Mapped[Optional[int]]
    details: Mapped[dict] = mapped_column(JSONType, default=dict)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
