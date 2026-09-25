"""
Precision AI - Retrieval (the "R" of RAG) with context validation.

FAISS returns (id, cosine) pairs; the rows are then loaded from PostgreSQL, and every hit is
validated: the row must still exist and be active, and must belong to the ticket's category
(general, uncategorised documents are allowed for KB chunks). Solutions are ranked by
similarity weighted by their trust level so human-verified knowledge outranks AI output.
"""

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.ticket import SolutionConfidence, Ticket, TicketSolution, TicketStatus
from app.vector_store import KNOWLEDGE, SOLUTIONS, TICKETS, get_index_manager

settings = get_settings()


@dataclass
class SolutionHit:
    solution: TicketSolution
    similarity: float
    score: float
    source_ticket_number: Optional[str] = None

    @property
    def reusable_without_llm(self) -> bool:
        """LEVEL 3 gate: may this solution be returned directly, with no LLM call?"""
        s = self.solution
        if self.similarity < settings.SOLUTION_REUSE_THRESHOLD:
            return False
        if s.confidence_level in (SolutionConfidence.HUMAN_VERIFIED, SolutionConfidence.ADMIN_VERIFIED):
            return True
        # User-confirmed only: needs a track record and a stricter similarity bar
        return (s.confidence_level == SolutionConfidence.USER_CONFIRMED
                and (s.times_successful or 0) >= 2 and (s.success_rate or 0) >= 0.7
                and self.similarity >= settings.SOLUTION_REUSE_THRESHOLD + 0.08)


@dataclass
class ChunkHit:
    chunk: KnowledgeChunk
    similarity: float

    @property
    def ref(self) -> str:
        return f"KB-{self.chunk.id}"


@dataclass
class TicketHit:
    ticket: Ticket
    similarity: float


@dataclass
class Retrieval:
    solutions: list[SolutionHit] = field(default_factory=list)
    chunks: list[ChunkHit] = field(default_factory=list)
    similar_tickets: list[TicketHit] = field(default_factory=list)

    @property
    def hit_count(self) -> int:
        return len(self.solutions) + len(self.chunks)

    def summary(self) -> list[dict]:
        out = [{"type": "solution", "id": h.solution.id, "title": h.solution.title,
                "similarity": round(h.similarity, 3), "confidence_level": h.solution.confidence_level,
                "source_ticket": h.source_ticket_number} for h in self.solutions[:5]]
        out += [{"type": "knowledge", "id": h.chunk.id, "ref": h.ref, "title": h.chunk.document.title,
                 "similarity": round(h.similarity, 3)} for h in self.chunks[:5]]
        return out


def solution_score(sol: TicketSolution, similarity: float, intent: Optional[str]) -> float:
    trust = SolutionConfidence.TRUST.get(sol.confidence_level, 0.4)
    score = similarity * (0.75 + 0.25 * trust)
    if intent and sol.intent == intent:
        score += 0.05
    if sol.success_rate is not None:
        score += (sol.success_rate - 0.5) * 0.1
    return score


async def retrieve(db: AsyncSession, text: str, *, category_id: Optional[int], intent: Optional[str],
                   exclude_ticket_id: Optional[int] = None, k: int = 12) -> Retrieval:
    manager = get_index_manager()
    out = Retrieval()

    # --- verified / confirmed solutions ---
    sol_hits = dict(await manager.search(SOLUTIONS, text, k))
    if sol_hits:
        rows = (await db.execute(select(TicketSolution).where(TicketSolution.id.in_(sol_hits)))).unique().scalars().all()
        ticket_numbers = await _ticket_numbers(db, [s.ticket_id for s in rows if s.ticket_id])
        for s in rows:
            sim = sol_hits[s.id]
            if not s.is_active or s.rejected or s.confidence_level not in SolutionConfidence.REUSABLE:
                continue  # stale index entry; PostgreSQL is authoritative
            if category_id and s.category_id != category_id:
                continue
            if sim < settings.RELATED_SIMILARITY_THRESHOLD:
                continue
            out.solutions.append(SolutionHit(s, sim, solution_score(s, sim, intent),
                                             ticket_numbers.get(s.ticket_id) if s.ticket_id else None))
        out.solutions.sort(key=lambda h: h.score, reverse=True)

    # --- IT documentation chunks ---
    kb_hits = dict(await manager.search(KNOWLEDGE, text, k))
    if kb_hits:
        rows = (await db.execute(select(KnowledgeChunk).join(KnowledgeDocument).where(
            KnowledgeChunk.id.in_(kb_hits), KnowledgeDocument.is_active.is_(True)))).unique().scalars().all()
        for c in rows:
            sim = kb_hits[c.id]
            doc_cat = c.document.category_id
            if sim < settings.KB_RELEVANCE_THRESHOLD:
                continue
            if category_id and doc_cat and doc_cat != category_id:
                continue
            out.chunks.append(ChunkHit(c, sim))
        out.chunks.sort(key=lambda h: h.similarity, reverse=True)

    # --- similar historical tickets ---
    out.similar_tickets = await similar_tickets(db, text, category_id=category_id,
                                                exclude_ticket_id=exclude_ticket_id,
                                                min_similarity=settings.RELATED_SIMILARITY_THRESHOLD)
    return out


async def similar_tickets(db: AsyncSession, text: str, *, category_id: Optional[int],
                          exclude_ticket_id: Optional[int], min_similarity: float, k: int = 25,
                          statuses: Optional[tuple] = None,
                          cross_category_min: Optional[float] = None) -> list[TicketHit]:
    """Similar tickets from the same category. With `cross_category_min`, near-identical reports
    from another category also count (a misclassified report must not hide an outage)."""
    hits = dict(await get_index_manager().search(TICKETS, text, k))
    if exclude_ticket_id is not None:
        hits.pop(exclude_ticket_id, None)
    if not hits:
        return []
    q = select(Ticket).where(Ticket.id.in_(hits))
    if statuses:
        q = q.where(Ticket.status.in_(statuses))
    rows = (await db.execute(q)).unique().scalars().all()

    def same_category_or_near_identical(t: Ticket) -> bool:
        if not category_id or t.category_id == category_id:
            return True
        return cross_category_min is not None and hits[t.id] >= cross_category_min

    result = [TicketHit(t, hits[t.id]) for t in rows
              if hits[t.id] >= min_similarity and same_category_or_near_identical(t)]
    result.sort(key=lambda h: h.similarity, reverse=True)
    return result


async def _ticket_numbers(db: AsyncSession, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = await db.execute(select(Ticket.id, Ticket.ticket_number).where(Ticket.id.in_(ids)))
    return {r[0]: r[1] for r in rows.all()}


RESOLVED_STATES = (TicketStatus.RESOLVED, TicketStatus.CLOSED)
