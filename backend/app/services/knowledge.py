"""
Precision AI - Knowledge service
 * IT documentation: document -> chunks -> FAISS (knowledge index)
 * Solution lifecycle (self-improving loop):
     AI_GENERATED -> USER_CONFIRMED -> HUMAN_VERIFIED -> ADMIN_VERIFIED
   Only USER_CONFIRMED and above are retrievable; AI output is never promoted automatically
   without a user confirming it worked, and only humans can verify.
"""

import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database import utcnow
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.ticket import SolutionConfidence, Ticket, TicketSolution
from app.models.user import User
from app.vector_store import get_index_manager

logger = get_logger(__name__)

CHUNK_TARGET_CHARS = 900


def chunk_markdown(content: str) -> list[tuple[Optional[str], str]]:
    """Split on markdown headings, then pack paragraphs into ~CHUNK_TARGET_CHARS chunks.
    Numbered procedures are kept together where possible so steps are not split."""
    sections: list[tuple[Optional[str], list[str]]] = []
    heading: Optional[str] = None
    buf: list[str] = []
    for line in content.splitlines():
        m = re.match(r"^#{1,4}\s+(.*)", line)
        if m:
            if "".join(buf).strip():
                sections.append((heading, buf))
            heading, buf = m.group(1).strip(), []
        else:
            buf.append(line)
    if "".join(buf).strip():
        sections.append((heading, buf))

    chunks: list[tuple[Optional[str], str]] = []
    for head, lines in sections:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", "\n".join(lines)) if p.strip()]
        current = ""
        for para in paragraphs:
            if current and len(current) + len(para) > CHUNK_TARGET_CHARS:
                chunks.append((head, current.strip()))
                current = ""
            current += para + "\n\n"
        if current.strip():
            chunks.append((head, current.strip()))
    return chunks


def steps_from_text(text: str) -> list[str]:
    """Extract ordered steps from numbered or bulleted lines; fall back to sentences."""
    steps = [m.group(1).strip() for m in re.finditer(r"^\s*(?:\d+[.)]|[-*•])\s+(.+)$", text, re.M)]
    if not steps:
        steps = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 15][:6]
    return [re.sub(r"\*\*(.+?)\*\*", r"\1", s) for s in steps][:10]


# ---------------- documents ----------------
async def create_document(db: AsyncSession, *, title: str, content: str, category_id: Optional[int],
                          doc_type: str = "runbook", source: str = "it_documentation",
                          trust_level: str = SolutionConfidence.ADMIN_VERIFIED,
                          created_by: Optional[int] = None, index: bool = True) -> KnowledgeDocument:
    doc = KnowledgeDocument(title=title, content=content, category_id=category_id, doc_type=doc_type,
                            source=source, trust_level=trust_level, created_by=created_by)
    db.add(doc)
    await db.flush()
    chunks = [KnowledgeChunk(document_id=doc.id, chunk_index=i, heading=h, content=c)
              for i, (h, c) in enumerate(chunk_markdown(content))]
    db.add_all(chunks)
    await db.flush()
    if index:
        await get_index_manager().index_chunks(chunks, title)
    logger.info("knowledge_document_created", document_id=doc.id, chunks=len(chunks))
    return doc


async def update_document(db: AsyncSession, doc: KnowledgeDocument, *, title: Optional[str] = None,
                          content: Optional[str] = None, category_id: Optional[int] = None,
                          is_active: Optional[bool] = None) -> KnowledgeDocument:
    old_ids = [c.id for c in doc.chunks]
    if title is not None:
        doc.title = title
    if category_id is not None:
        doc.category_id = category_id
    if is_active is not None:
        doc.is_active = is_active
    manager = get_index_manager()
    if content is not None and content != doc.content:
        doc.content = content
        for c in list(doc.chunks):
            await db.delete(c)
        await db.flush()
        new_chunks = [KnowledgeChunk(document_id=doc.id, chunk_index=i, heading=h, content=c)
                      for i, (h, c) in enumerate(chunk_markdown(content))]
        db.add_all(new_chunks)
        await db.flush()
        await manager.remove_chunks(old_ids)
        if doc.is_active:
            await manager.index_chunks(new_chunks, doc.title)
    elif is_active is False:
        await manager.remove_chunks(old_ids)
    elif is_active is True or title is not None:
        await manager.index_chunks(list(doc.chunks), doc.title)
    return doc


# ---------------- solutions ----------------
async def create_solution(db: AsyncSession, *, title: str, problem: str, solution: str, steps: list[str],
                          category_id: Optional[int], intent: Optional[str], confidence_level: str,
                          source: str, ticket_id: Optional[int] = None, symptoms: Optional[str] = None,
                          root_cause: Optional[str] = None, automated_actions: Optional[list[str]] = None,
                          created_by: Optional[int] = None, verified_by: Optional[int] = None,
                          index: bool = True) -> TicketSolution:
    if confidence_level not in SolutionConfidence.ORDER:
        raise ValueError("invalid confidence level")
    sol = TicketSolution(
        ticket_id=ticket_id, category_id=category_id, intent=intent, title=title[:300],
        problem_description=problem, symptoms=symptoms, root_cause=root_cause,
        solution_description=solution, steps=steps, automated_actions=automated_actions or [],
        confidence_level=confidence_level, source=source, created_by=created_by,
        verified_by=verified_by, verified_at=utcnow() if verified_by else None,
    )
    db.add(sol)
    await db.flush()
    if index:
        await get_index_manager().sync_solution(sol)
    return sol


async def promote_solution(db: AsyncSession, sol: TicketSolution, level: str, user: Optional[User]) -> TicketSolution:
    """Raise a solution's trust level (never lowers it)."""
    order = SolutionConfidence.ORDER
    if order.index(level) > order.index(sol.confidence_level):
        sol.confidence_level = level
        if level in (SolutionConfidence.HUMAN_VERIFIED, SolutionConfidence.ADMIN_VERIFIED) and user:
            sol.verified_by, sol.verified_at = user.id, utcnow()
    sol.rejected = False
    sol.is_active = True
    await db.flush()
    await get_index_manager().sync_solution(sol)
    return sol


async def reject_solution(db: AsyncSession, sol: TicketSolution, user: User) -> TicketSolution:
    sol.rejected = True
    sol.is_active = False
    await db.flush()
    await get_index_manager().sync_solution(sol)
    logger.info("solution_rejected", solution_id=sol.id, by=user.id)
    return sol


async def record_outcome(db: AsyncSession, sol: TicketSolution, success: bool) -> None:
    sol.times_used = (sol.times_used or 0) + 1
    if success:
        sol.times_successful = (sol.times_successful or 0) + 1
    else:
        sol.times_failed = (sol.times_failed or 0) + 1
    # A solution that keeps failing is withdrawn from retrieval until a human reviews it
    if sol.times_failed >= 3 and (sol.success_rate or 0) < 0.4 and sol.confidence_level != SolutionConfidence.ADMIN_VERIFIED:
        sol.is_active = False
        logger.warning("solution_auto_withdrawn", solution_id=sol.id, success_rate=sol.success_rate)
    await db.flush()
    await get_index_manager().sync_solution(sol)


async def capture_resolution(db: AsyncSession, ticket: Ticket, *, solution_text: str, steps: list[str],
                             confidence_level: str, source: str, root_cause: Optional[str] = None,
                             user: Optional[User] = None,
                             automated_actions: Optional[list[str]] = None) -> TicketSolution:
    """Turn a resolved ticket into a knowledge entry (the self-improving loop)."""
    existing = (await db.execute(select(TicketSolution).where(
        TicketSolution.ticket_id == ticket.id, TicketSolution.solution_description == solution_text,
    ))).unique().scalar_one_or_none()
    if existing:
        return await promote_solution(db, existing, confidence_level, user)
    return await create_solution(
        db, title=ticket.title, problem=ticket.description, solution=solution_text, steps=steps,
        category_id=ticket.category_id, intent=ticket.intent, confidence_level=confidence_level,
        source=source, ticket_id=ticket.id, root_cause=root_cause, automated_actions=automated_actions,
        symptoms=", ".join(f"{k}: {v}" for k, v in (ticket.entities or {}).items()) or None,
        created_by=user.id if user else None,
        verified_by=user.id if user and confidence_level in (SolutionConfidence.HUMAN_VERIFIED,
                                                            SolutionConfidence.ADMIN_VERIFIED) else None,
    )
