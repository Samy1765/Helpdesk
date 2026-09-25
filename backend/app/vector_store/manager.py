"""
Precision AI - Index manager.
Owns three FAISS indexes that reference PostgreSQL ids:

  tickets    -> tickets.id              (duplicate detection, incident correlation, history)
  solutions  -> ticket_solutions.id     (only reusable: user_confirmed and above, active)
  knowledge  -> knowledge_chunks.id     (RAG over IT documentation)

On startup each index is loaded from disk and compared with the ids in the database; any
drift (missing file, other embedder, different id set) triggers a rebuild from PostgreSQL.
"""

import asyncio
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.embeddings import embed, get_embedder
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.ticket import SolutionConfidence, Ticket, TicketSolution
from app.vector_store.faiss_store import FaissVectorStore, open_store

logger = get_logger(__name__)

TICKETS, SOLUTIONS, KNOWLEDGE = "tickets", "solutions", "knowledge"


def ticket_text(t: Ticket) -> str:
    return f"{t.title}. {t.description}"[:2000]


def solution_text(s: TicketSolution) -> str:
    return f"{s.title}. {s.problem_description}. {s.symptoms or ''}"[:2000]


def chunk_text(c: KnowledgeChunk, doc_title: str) -> str:
    return f"{doc_title} - {c.heading or ''}: {c.content}"[:2000]


def solution_is_indexable(s: TicketSolution) -> bool:
    return bool(s.is_active and not s.rejected and s.confidence_level in SolutionConfidence.REUSABLE)


class IndexManager:
    def __init__(self, directory: Optional[str] = None):
        self.directory = directory or get_settings().FAISS_INDEX_DIR
        self.stores: dict[str, FaissVectorStore] = {}
        self._lock = asyncio.Lock()
        self.ready = False

    def _open(self) -> dict[str, bool]:
        emb = get_embedder()
        loaded = {}
        for name in (TICKETS, SOLUTIONS, KNOWLEDGE):
            self.stores[name], loaded[name] = open_store(name, emb.dim, self.directory, emb.name)
        return loaded

    # ---------- startup / rebuild ----------
    async def initialize(self, db: AsyncSession) -> dict:
        """Load indexes, verify against the DB, rebuild what is stale."""
        async with self._lock:
            loaded = await asyncio.to_thread(self._open)
            report = {}
            for name in (TICKETS, SOLUTIONS, KNOWLEDGE):
                db_ids = await self._db_ids(db, name)
                if loaded[name] and self.stores[name].ids() == db_ids:
                    report[name] = {"action": "loaded", "count": len(db_ids)}
                else:
                    count = await self._rebuild(db, name)
                    report[name] = {"action": "rebuilt", "count": count}
            self.ready = True
            logger.info("vector_indexes_ready", **{k: v["action"] + ":" + str(v["count"]) for k, v in report.items()})
            return report

    async def rebuild_all(self, db: AsyncSession) -> dict:
        async with self._lock:
            if not self.stores:
                await asyncio.to_thread(self._open)
            report = {name: {"action": "rebuilt", "count": await self._rebuild(db, name)}
                      for name in (TICKETS, SOLUTIONS, KNOWLEDGE)}
            self.ready = True
            return report

    async def _db_ids(self, db: AsyncSession, name: str) -> set[int]:
        if name == TICKETS:
            rows = await db.execute(select(Ticket.id))
        elif name == SOLUTIONS:
            rows = await db.execute(select(TicketSolution.id).where(
                TicketSolution.is_active.is_(True), TicketSolution.rejected.is_(False),
                TicketSolution.confidence_level.in_(SolutionConfidence.REUSABLE)))
        else:
            rows = await db.execute(select(KnowledgeChunk.id).join(KnowledgeDocument).where(
                KnowledgeDocument.is_active.is_(True)))
        return {r[0] for r in rows.all()}

    async def _rebuild(self, db: AsyncSession, name: str) -> int:
        store = self.stores[name]
        store.reset()
        ids, texts = await self._collect(db, name)
        batch = 256
        for i in range(0, len(ids), batch):
            vecs = await embed(texts[i:i + batch])
            store.upsert(ids[i:i + batch], vecs)
        await asyncio.to_thread(store.persist)
        return len(ids)

    async def _collect(self, db: AsyncSession, name: str) -> tuple[list[int], list[str]]:
        if name == TICKETS:
            rows = (await db.execute(select(Ticket))).unique().scalars().all()
            return [t.id for t in rows], [ticket_text(t) for t in rows]
        if name == SOLUTIONS:
            rows = (await db.execute(select(TicketSolution))).unique().scalars().all()
            rows = [s for s in rows if solution_is_indexable(s)]
            return [s.id for s in rows], [solution_text(s) for s in rows]
        rows = (await db.execute(select(KnowledgeChunk).join(KnowledgeDocument).where(
            KnowledgeDocument.is_active.is_(True)))).unique().scalars().all()
        return [c.id for c in rows], [chunk_text(c, c.document.title) for c in rows]

    # ---------- incremental updates ----------
    async def _upsert(self, name: str, ids: list[int], texts: list[str]):
        if not ids:
            return
        vecs = await embed(texts)
        async with self._lock:
            store = self.stores[name]
            store.upsert(ids, vecs)
            await asyncio.to_thread(store.persist)

    async def _remove(self, name: str, ids: list[int]):
        if not ids:
            return
        async with self._lock:
            store = self.stores[name]
            store.remove(ids)
            await asyncio.to_thread(store.persist)

    async def index_ticket(self, ticket: Ticket):
        await self._upsert(TICKETS, [ticket.id], [ticket_text(ticket)])

    async def sync_solution(self, solution: TicketSolution):
        """Index if reusable, otherwise make sure it is not retrievable."""
        if solution_is_indexable(solution):
            await self._upsert(SOLUTIONS, [solution.id], [solution_text(solution)])
        else:
            await self._remove(SOLUTIONS, [solution.id])

    async def index_chunks(self, chunks: list[KnowledgeChunk], doc_title: str):
        await self._upsert(KNOWLEDGE, [c.id for c in chunks], [chunk_text(c, doc_title) for c in chunks])

    async def remove_chunks(self, chunk_ids: list[int]):
        await self._remove(KNOWLEDGE, chunk_ids)

    # ---------- search ----------
    async def search(self, name: str, text: str, k: int = 10) -> list[tuple[int, float]]:
        store = self.stores.get(name)
        if store is None or len(store) == 0:
            return []
        vec = (await embed([text]))[0]
        return store.search(vec, k)

    def stats(self) -> dict:
        emb = get_embedder()
        return {"embedder": emb.name, "dim": emb.dim,
                "indexes": {name: len(store) for name, store in self.stores.items()}}


_manager: Optional[IndexManager] = None


def get_index_manager() -> IndexManager:
    global _manager
    if _manager is None:
        _manager = IndexManager()
    return _manager


def set_index_manager(manager: IndexManager):
    """Used by tests to point at a temporary directory."""
    global _manager
    _manager = manager
