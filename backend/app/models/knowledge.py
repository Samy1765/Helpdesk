"""
Precision AI - Knowledge base models (documents + chunks for RAG).
PostgreSQL is the source of truth; FAISS only indexes chunk ids.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base, utcnow

if TYPE_CHECKING:
    from app.models.ticket import TicketCategory


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    doc_type: Mapped[str] = mapped_column(String(40), default="runbook")  # runbook | faq | guide | policy
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ticket_categories.id"), index=True)
    source: Mapped[str] = mapped_column(String(40), default="it_documentation")
    # Same trust ladder as solutions; official IT documentation is admin_verified
    trust_level: Mapped[str] = mapped_column(String(30), default="admin_verified")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    category: Mapped[Optional["TicketCategory"]] = relationship(lazy="joined")
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="KnowledgeChunk.chunk_index")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int]
    heading: Mapped[Optional[str]] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped["KnowledgeDocument"] = relationship(back_populates="chunks", lazy="joined")
