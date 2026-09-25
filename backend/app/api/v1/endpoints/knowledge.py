"""
Precision AI - Knowledge base: browse, semantic search, and (staff) authoring.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import document_out, solution_out
from app.core.deps import STAFF_ROLES, get_current_user, require_role
from app.database import get_db
from app.models.knowledge import KnowledgeDocument
from app.models.ticket import SolutionConfidence, TicketCategory
from app.models.user import User
from app.rag.retriever import retrieve
from app.services import knowledge, tickets as ticket_svc

router = APIRouter(prefix="/knowledge", tags=["Knowledge base"])


class DocumentIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    content: str = Field(min_length=20, max_length=50000)
    category_id: Optional[int] = None
    doc_type: str = Field(default="runbook", pattern="^(runbook|faq|guide|policy)$")


class DocumentUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=300)
    content: Optional[str] = Field(default=None, min_length=20, max_length=50000)
    category_id: Optional[int] = None
    is_active: Optional[bool] = None


@router.get("/documents")
async def list_documents(q: Optional[str] = Query(None, max_length=100), category_id: Optional[int] = None,
                         db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(KnowledgeDocument).where(KnowledgeDocument.is_active.is_(True))
    if category_id:
        query = query.where(KnowledgeDocument.category_id == category_id)
    if q:
        like = f"%{q}%"
        query = query.where(or_(KnowledgeDocument.title.ilike(like), KnowledgeDocument.content.ilike(like)))
    rows = (await db.execute(query.order_by(KnowledgeDocument.title))).unique().scalars().all()
    return [document_out(d, include_content=False) for d in rows]


@router.get("/documents/{doc_id}")
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    doc = await db.get(KnowledgeDocument, doc_id)
    if doc is None or (not doc.is_active and user.role_name == "employee"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document_out(doc)


@router.get("/search")
async def semantic_search(q: str = Query(min_length=3, max_length=500), category_id: Optional[int] = None,
                          db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Semantic search over verified solutions and IT documentation (FAISS + PostgreSQL)."""
    r = await retrieve(db, q, category_id=category_id, intent=None)
    return {
        "documents": [{"chunk_id": h.chunk.id, "ref": h.ref, "document_id": h.chunk.document_id,
                       "title": h.chunk.document.title, "heading": h.chunk.heading,
                       "excerpt": h.chunk.content[:400], "similarity": round(h.similarity, 3),
                       "category": h.chunk.document.category.name if h.chunk.document.category else None}
                      for h in r.chunks[:8]],
        "solutions": [{**solution_out(h.solution, h.source_ticket_number), "similarity": round(h.similarity, 3)}
                      for h in r.solutions[:6]],
    }


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def create_document(data: DocumentIn, db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_role(*STAFF_ROLES))):
    if data.category_id and await db.get(TicketCategory, data.category_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown category")
    level = SolutionConfidence.ADMIN_VERIFIED if user.role_name == "admin" else SolutionConfidence.HUMAN_VERIFIED
    doc = await knowledge.create_document(db, title=data.title, content=data.content, category_id=data.category_id,
                                          doc_type=data.doc_type, source="admin", trust_level=level,
                                          created_by=user.id)
    await ticket_svc.audit(db, "kb_document_created", user_id=user.id, resource_type="knowledge_document",
                           resource_id=doc.id)
    await db.refresh(doc)
    return document_out(doc)


@router.patch("/documents/{doc_id}")
async def update_document(doc_id: int, data: DocumentUpdate, db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_role(*STAFF_ROLES))):
    doc = await db.get(KnowledgeDocument, doc_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    await db.refresh(doc, ["chunks"])
    await knowledge.update_document(db, doc, **data.model_dump(exclude_unset=True))
    await ticket_svc.audit(db, "kb_document_updated", user_id=user.id, resource_type="knowledge_document",
                           resource_id=doc.id)
    await db.refresh(doc)
    return document_out(doc)
