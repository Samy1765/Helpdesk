"""
Precision AI - User and Role Models
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base, JSONType, utcnow

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.ticket import Ticket


class Role(Base):
    """User roles: employee, it_support, admin."""
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    permissions: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base):
    """Application users - employees, IT support agents, and administrators."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    # For employees: their business unit. For IT staff: the support team they belong to.
    department_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"))
    job_title: Mapped[Optional[str]] = mapped_column(String(150))
    location: Mapped[Optional[str]] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(default=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    role: Mapped["Role"] = relationship(back_populates="users", lazy="joined")
    department: Mapped[Optional["Department"]] = relationship(back_populates="users", lazy="joined")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="creator", foreign_keys="Ticket.user_id")
    assigned_tickets: Mapped[list["Ticket"]] = relationship(back_populates="assignee",
                                                            foreign_keys="Ticket.assigned_to")

    @property
    def role_name(self) -> str:
        return self.role.name if self.role else "employee"
