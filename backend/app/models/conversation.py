"""
Precision AI - Chat conversation state (persisted; survives restarts and multiple workers).
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base, JSONType, utcnow

if TYPE_CHECKING:
    from app.models.ticket import Ticket


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # intake -> clarifying -> agent -> closed
    stage: Mapped[str] = mapped_column(String(30), default="intake")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active | closed
    # Slots collected during intake (description, answers, user priority, client environment...)
    slots: Mapped[dict] = mapped_column(JSONType, default=dict)
    ticket_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tickets.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    ticket: Mapped[Optional["Ticket"]] = relationship(lazy="joined")
