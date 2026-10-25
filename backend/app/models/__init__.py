"""Import all models so SQLAlchemy metadata (and Alembic) sees every table."""

from app.models.department import Department
from app.models.user import Role, User
from app.models.ticket import (
    SolutionConfidence, Ticket, TicketAssignment, TicketCategory, TicketEscalation, TicketEvent,
    TicketFeedback, TicketMessage, TicketSolution, TicketStatus, TroubleshootingStep,
)
from app.models.agent import AgentAction, AgentRun, AuditLog, Incident, LLMUsageLog
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.conversation import Conversation
from app.models.attachment import Attachment
from app.models.auth import AuthSession, LoginThrottle

__all__ = [
    "Attachment", "AuthSession", "LoginThrottle",
    "Department", "Role", "User", "SolutionConfidence", "Ticket", "TicketAssignment",
    "TicketCategory", "TicketEscalation", "TicketEvent", "TicketFeedback", "TicketMessage",
    "TicketSolution", "TicketStatus", "TroubleshootingStep", "AgentAction", "AgentRun",
    "AuditLog", "Incident", "LLMUsageLog", "KnowledgeChunk", "KnowledgeDocument", "Conversation",
]
