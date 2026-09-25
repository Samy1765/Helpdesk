"""FAISS persistence/rebuild, semantic similarity, retrieval with context validation, knowledge lifecycle."""

import numpy as np
from sqlalchemy import select

from app.embeddings import embed
from app.models import KnowledgeChunk, SolutionConfidence, TicketCategory, TicketSolution
from app.rag.retriever import retrieve
from app.services import knowledge
from app.services.knowledge import chunk_markdown, steps_from_text
from app.vector_store import SOLUTIONS, IndexManager, get_index_manager
from app.vector_store.faiss_store import FaissVectorStore


def test_faiss_store_add_search_remove_persist(tmp_path):
    store = FaissVectorStore("t", 4, str(tmp_path), "unit")
    vecs = np.eye(4, dtype="float32")
    store.upsert([10, 20, 30], vecs[:3])
    assert store.search(vecs[1], 1)[0][0] == 20
    store.upsert([20], vecs[3:4])  # re-index is idempotent (replaces the vector)
    assert len(store) == 3 and store.search(vecs[3], 1)[0][0] == 20
    store.remove([10])
    assert store.ids() == {20, 30}
    store.persist()
    reloaded = FaissVectorStore("t", 4, str(tmp_path), "unit")
    assert reloaded.load() and reloaded.ids() == {20, 30}
    # an index built with another embedder is not trusted
    other = FaissVectorStore("t", 4, str(tmp_path), "different-embedder")
    assert other.load() is False


async def test_semantic_similarity_of_paraphrases():
    v = await embed(["VPN doesn't connect.", "Unable to access office VPN.", "The printer is out of toner"])
    assert float(v[0] @ v[1]) > 0.6
    assert float(v[0] @ v[2]) < 0.3


async def test_index_manager_detects_drift_and_rebuilds(db, tmp_path):
    mgr = IndexManager(str(tmp_path / "idx"))
    first = await mgr.initialize(db)
    assert all(v["action"] == "rebuilt" for v in first.values())
    second = await IndexManager(str(tmp_path / "idx")).initialize(db)
    assert all(v["action"] == "loaded" for v in second.values())
    mgr.stores[SOLUTIONS].remove(list(mgr.stores[SOLUTIONS].ids())[:1])  # simulate drift
    mgr.stores[SOLUTIONS].persist()
    third = await IndexManager(str(tmp_path / "idx")).initialize(db)
    assert third[SOLUTIONS]["action"] == "rebuilt"


async def test_retrieval_finds_verified_solution_and_gates_category(db):
    vpn = (await db.execute(select(TicketCategory).where(TicketCategory.name == "VPN"))).unique().scalar_one()
    printer = (await db.execute(select(TicketCategory).where(TicketCategory.name == "Printer"))).unique().scalar_one()
    text = "VPN authentication times out after I type my MFA code on the Windows laptop"
    r = await retrieve(db, text, category_id=vpn.id, intent="vpn_mfa_failure")
    assert r.solutions, "expected the human-verified VPN solution"
    top = r.solutions[0]
    assert top.solution.category_id == vpn.id
    assert top.reusable_without_llm
    assert r.chunks and all(c.chunk.document.category_id in (vpn.id, None) for c in r.chunks)
    # same text, wrong category: no VPN knowledge may leak through
    r2 = await retrieve(db, text, category_id=printer.id, intent=None)
    assert all(h.solution.category_id == printer.id for h in r2.solutions)


async def test_ai_generated_solutions_are_not_retrievable_until_confirmed(db):
    vpn = (await db.execute(select(TicketCategory).where(TicketCategory.name == "VPN"))).unique().scalar_one()
    sol = await knowledge.create_solution(
        db, title="Zyxel tunnel frobnication fix", problem="Zyxel frobnicator tunnel refuses handshake",
        solution="Toggle the frobnicator", steps=["Toggle it"], category_id=vpn.id, intent=None,
        confidence_level=SolutionConfidence.AI_GENERATED, source="ai")
    assert sol.id not in get_index_manager().stores[SOLUTIONS].ids()
    await knowledge.promote_solution(db, sol, SolutionConfidence.USER_CONFIRMED, None)
    assert sol.id in get_index_manager().stores[SOLUTIONS].ids()
    await knowledge.reject_solution(db, sol, user=type("U", (), {"id": 1})())
    assert sol.id not in get_index_manager().stores[SOLUTIONS].ids()


async def test_failing_solution_is_withdrawn(db):
    sol = (await db.execute(select(TicketSolution).where(
        TicketSolution.confidence_level == SolutionConfidence.USER_CONFIRMED))).unique().scalars().first()
    sol.times_successful, sol.times_failed = 0, 2
    await knowledge.record_outcome(db, sol, success=False)
    assert sol.is_active is False
    assert sol.id not in get_index_manager().stores[SOLUTIONS].ids()
    await db.rollback()
    await get_index_manager().rebuild_all(db)  # restore index for other tests


def test_chunking_and_step_extraction():
    doc = "# Title\n\n## Part A\n1. First step\n2. Second step\n\n## Part B\nSome text here that is long enough."
    chunks = chunk_markdown(doc)
    assert [h for h, _ in chunks] == ["Part A", "Part B"]
    assert steps_from_text(chunks[0][1]) == ["First step", "Second step"]


async def test_knowledge_document_indexed_on_create(db):
    doc = await knowledge.create_document(db, title="Plotter calibration", content="## Calibrate\n1. Open menu\n2. Run calibration wizard",
                                          category_id=None)
    ids = {c.id for c in (await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))).unique().scalars()}
    assert ids and ids <= get_index_manager().stores["knowledge"].ids()
    await db.rollback()
    await get_index_manager().rebuild_all(db)
