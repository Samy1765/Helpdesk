"""
Precision AI - Ticket and Related Models
Tickets, messages, events, assignments, solutions, troubleshooting steps, feedback, escalations.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base, JSONType, utcnow

if TYPE_CHECKING:
    from app.models.agent import AgentRun, Incident
    from app.models.department import Department
    from app.models.user import User


class TicketStatus:
    NEW = "new"
    AI_ANALYSIS = "ai_analysis"
    TROUBLESHOOTING = "troubleshooting"
    AWAITING_USER = "awaiting_user"
    AWAITING_APPROVAL = "awaiting_approval"
    ESCALATED = "escalated"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    DUPLICATE = "duplicate"
    LINKED_INCIDENT = "linked_incident"

    OPEN = (NEW, AI_ANALYSIS, TROUBLESHOOTING, AWAITING_USER, AWAITING_APPROVAL,
            ESCALATED, ASSIGNED, IN_PROGRESS, LINKED_INCIDENT)
    DONE = (RESOLVED, CLOSED, DUPLICATE)
    ALL = OPEN + DONE


class SolutionConfidence:
    """Trust ladder for stored solutions. Higher levels get higher retrieval priority."""
    AI_GENERATED = "ai_generated"
    USER_CONFIRMED = "user_confirmed"
    HUMAN_VERIFIED = "human_verified"
    ADMIN_VERIFIED = "admin_verified"

    ORDER = [AI_GENERATED, USER_CONFIRMED, HUMAN_VERIFIED, ADMIN_VERIFIED]
    TRUST = {AI_GENERATED: 0.4, USER_CONFIRMED: 0.75, HUMAN_VERIFIED: 0.9, ADMIN_VERIFIED: 1.0}
    # Levels that may become retrievable knowledge
    REUSABLE = (USER_CONFIRMED, HUMAN_VERIFIED, ADMIN_VERIFIED)


class TicketCategory(Base):
    """Ticket categories mapped to the owning support department. Extensible at runtime."""
    __tablename__ = "ticket_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    department_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"))
    keywords: Mapped[list] = mapped_column(JSONType, default=list)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    department: Mapped[Optional["Department"]] = relationship(back_populates="categories", lazy="joined")


class Ticket(Base):
    """Core ticket record."""
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_status_created", "status", "created_at"),
        Index("ix_tickets_category_created", "category_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_number: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)

    # Classification
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ticket_categories.id"))
    sub_category: Mapped[Optional[str]] = mapped_column(String(100))
    intent: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    entities: Mapped[dict] = mapped_column(JSONType, default=dict)
    ai_confidence: Mapped[Optional[float]]
    classification_method: Mapped[Optional[str]] = mapped_column(String(30))  # rules | llm | rules+llm | manual

    # Priority
    user_priority: Mapped[Optional[str]] = mapped_column(String(20))
    system_priority: Mapped[Optional[str]] = mapped_column(String(20))
    priority: Mapped[str] = mapped_column(String(20), default="medium", index=True)  # effective priority
    priority_confidence: Mapped[Optional[float]]
    priority_reason: Mapped[Optional[str]] = mapped_column(Text)
    priority_impact: Mapped[Optional[str]] = mapped_column(String(300))
    priority_urgency: Mapped[Optional[str]] = mapped_column(String(300))

    status: Mapped[str] = mapped_column(String(30), default=TicketStatus.NEW, index=True)
    source: Mapped[str] = mapped_column(String(30), default="ai_chatbot")

    # Routing
    assigned_to: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), index=True)
    department_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"))
    incident_id: Mapped[Optional[int]] = mapped_column(ForeignKey("incidents.id"), index=True)
    duplicate_of_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tickets.id"))

    # Resolution
    resolved_by_ai: Mapped[bool] = mapped_column(default=False)
    resolution_summary: Mapped[Optional[str]] = mapped_column(Text)
    extra_data: Mapped[dict] = mapped_column(JSONType, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    category: Mapped[Optional["TicketCategory"]] = relationship(lazy="joined")
    creator: Mapped["User"] = relationship(back_populates="tickets", foreign_keys=[user_id], lazy="joined")
    assignee: Mapped[Optional["User"]] = relationship(back_populates="assigned_tickets",
                                                      foreign_keys=[assigned_to], lazy="joined")
    department: Mapped[Optional["Department"]] = relationship(back_populates="tickets", lazy="joined")
    incident: Mapped[Optional["Incident"]] = relationship(back_populates="tickets")
    duplicate_of: Mapped[Optional["Ticket"]] = relationship(remote_side=[id])
    messages: Mapped[list["TicketMessage"]] = relationship(back_populates="ticket", order_by="TicketMessage.id")
    events: Mapped[list["TicketEvent"]] = relationship(back_populates="ticket", order_by="TicketEvent.id")
    solutions: Mapped[list["TicketSolution"]] = relationship(back_populates="ticket")
    troubleshooting_steps: Mapped[list["TroubleshootingStep"]] = relationship(
        back_populates="ticket", order_by="TroubleshootingStep.id")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="ticket")

    @property
    def category_name(self) -> Optional[str]:
        return self.category.name if self.category else None


class TicketMessage(Base):
    """
    Conversation messages. Messages exchanged before a ticket exists belong only to the
    conversation; they are attached to the ticket once it is generated.
    """
    __tablename__ = "ticket_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("conversations.id"), index=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tickets.id"), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | system | agent
    content: Mapped[str] = mapped_column(Text)
    is_internal: Mapped[bool] = mapped_column(default=False)  # IT-only notes
    # Structured card payload (alerts, solution, progress) so the chat UI can re-render history
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    ticket: Mapped[Optional["Ticket"]] = relationship(back_populates="messages")
    author: Mapped[Optional["User"]] = relationship(lazy="joined")


class TicketEvent(Base):
    """Audit trail of all ticket state changes."""
    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    old_value: Mapped[Optional[str]] = mapped_column(String(300))
    new_value: Mapped[Optional[str]] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    ticket: Mapped["Ticket"] = relationship(back_populates="events")
    actor: Mapped[Optional["User"]] = relationship(lazy="joined")


class TicketAssignment(Base):
    """History of ticket assignments."""
    __tablename__ = "ticket_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    assigned_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    assigned_to: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TicketSolution(Base):
    """
    Stored solutions with a confidence ladder. Only USER_CONFIRMED and above become
    retrievable knowledge; AI_GENERATED solutions are kept for review, never reused blindly.
    """
    __tablename__ = "ticket_solutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tickets.id"), index=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ticket_categories.id"), index=True)
    intent: Mapped[Optional[str]] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(300))
    problem_description: Mapped[str] = mapped_column(Text)
    symptoms: Mapped[Optional[str]] = mapped_column(Text)
    root_cause: Mapped[Optional[str]] = mapped_column(Text)
    solution_description: Mapped[str] = mapped_column(Text)
    steps: Mapped[list] = mapped_column(JSONType, default=list)              # ordered user-facing steps
    automated_actions: Mapped[list] = mapped_column(JSONType, default=list)  # registered tool names only
    confidence_level: Mapped[str] = mapped_column(String(30), default=SolutionConfidence.AI_GENERATED)
    source: Mapped[str] = mapped_column(String(30), default="ai")  # ai | agent | it_support | admin | documentation
    times_used: Mapped[int] = mapped_column(default=0)
    times_successful: Mapped[int] = mapped_column(default=0)
    times_failed: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    rejected: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    verified_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    ticket: Mapped[Optional["Ticket"]] = relationship(back_populates="solutions")
    category: Mapped[Optional["TicketCategory"]] = relationship(lazy="joined")

    @property
    def success_rate(self) -> Optional[float]:
        total = (self.times_successful or 0) + (self.times_failed or 0)
        return round(self.times_successful / total, 3) if total else None


class TroubleshootingStep(Base):
    """Visible execution log of the agent and humans (no hidden reasoning)."""
    __tablename__ = "troubleshooting_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    agent_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("agent_runs.id"))
    step_key: Mapped[str] = mapped_column(String(40))  # agent state or 'manual'
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="completed")  # completed | running | failed | skipped
    performed_by: Mapped[str] = mapped_column(String(20), default="agent")  # agent | user | it_support
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    ticket: Mapped["Ticket"] = relationship(back_populates="troubleshooting_steps")


class TicketFeedback(Base):
    """User confirmation / feedback on a proposed resolution."""
    __tablename__ = "ticket_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    solution_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ticket_solutions.id"))
    issue_resolved: Mapped[bool]
    satisfaction_rating: Mapped[Optional[int]]
    comments: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TicketEscalation(Base):
    """Escalation package handed to a human support team."""
    __tablename__ = "ticket_escalations"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    reason: Mapped[str] = mapped_column(Text)
    package: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    department: Mapped["Department"] = relationship(lazy="joined")
