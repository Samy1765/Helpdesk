"""
Precision AI - Department Model
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base, utcnow

if TYPE_CHECKING:
    from app.models.agent import Incident
    from app.models.ticket import Ticket, TicketCategory
    from app.models.user import User


class Department(Base):
    """Departments: IT support teams (escalation targets) and business units."""
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    escalation_email: Mapped[Optional[str]] = mapped_column(String(255))
    is_support_team: Mapped[bool] = mapped_column(default=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="department")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="department")
    categories: Mapped[list["TicketCategory"]] = relationship(back_populates="department")
    incidents: Mapped[list["Incident"]] = relationship(back_populates="department")
