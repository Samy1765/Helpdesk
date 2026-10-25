"""Knowledge base content and the L3 path: runbook structure, review metadata, verified solutions reused without an
LLM, procedure selection, FAISS rebuild from the database, and separation from the evaluation set."""

import json
import re
from datetime import date

import pytest
from sqlalchemy import select

from app.core.config import PROJECT_DIR
from app.database.seed import CATEGORY_DEPARTMENT, DEPARTMENTS, parse_front_matter
from app.models import KnowledgeChunk, KnowledgeDocument, SolutionConfidence, TicketCategory, TicketSolution
from app.rag.retriever import ChunkHit, procedure_for, retrieve
from app.services.knowledge import chunk_markdown, is_procedure, steps_from_text
from app.vector_store import KNOWLEDGE, SOLUTIONS, TICKETS, IndexManager
from tests.conftest import new_employee

KB = sorted((PROJECT_DIR / "data" / "knowledge").glob("*.md"))
SOLUTIONS_SPEC = json.loads((PROJECT_DIR / "data" / "seed" / "verified_solutions.json").read_text(encoding="utf-8"))["solutions"]
TEAM_NAME = {code: name for name, code, _, _ in DEPARTMENTS}


def test_knowledge_base_covers_every_category():
    cats = [parse_front_matter(p.read_text(encoding="utf-8"))[0]["category"] for p in KB]
    assert len(KB) >= 40
    assert set(cats) == set(CATEGORY_DEPARTMENT)
    assert min(cats.count(c) for c in CATEGORY_DEPARTMENT) >= 3


@pytest.mark.parametrize("path", KB, ids=lambda p: p.stem)
def test_runbook_structure_and_review_metadata(path):
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
    assert meta["title"] and meta["doc_type"] in ("runbook", "guide", "faq", "policy")
    assert meta["owner"] == TEAM_NAME[CATEGORY_DEPARTMENT[meta["category"]]]  # owned by the team that gets escalations
    reviewed = date.fromisoformat(meta["last_reviewed"])
    assert date(2026, 1, 1) <= reviewed <= date.today()
    sections = dict(chunk_markdown(body))
    assert {"Symptoms", "Escalation criteria"} <= set(sections)
    procedures = [c for h, c in chunk_markdown(body) if h and h.startswith("Resolution")]
    assert procedures and all(len(steps_from_text(c)) >= 3 for c in procedures)
    assert all(is_procedure("Resolution", c) for c in procedures)
    assert not is_procedure("Symptoms", sections["Symptoms"]) and not is_procedure("Escalation criteria", sections["Escalation criteria"])
    # only the fictional company's addresses, or reserved .example domains in phishing examples
    assert all(a.endswith(("@acme-demo.in", ".example")) for a in re.findall(r"[\w.-]+@[\w.-]+\w", body))


async def test_documents_api_shows_owner_and_review_date(client):
    h, _ = await new_employee(client)
    docs = (await client.get("/api/v1/knowledge/documents", headers=h)).json()
    assert len(docs) >= 40
    vpn = next(d for d in docs if d["title"].startswith("GlobalProtect VPN fails"))
    assert vpn["owner"] == "Network Team" and vpn["last_reviewed"] == "2026-09-22"
    assert not vpn["excerpt"].startswith(("#", "-")) and "sign-in failures" in vpn["excerpt"]


async def test_editing_a_document_counts_as_a_review(client, db):
    from tests.conftest import login

    support = await login(client, "itsupport", "Support@123")
    doc = (await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.title.like("Desk network port%")))).unique().scalar_one()
    r = await client.patch(f"/api/v1/knowledge/documents/{doc.id}", headers=support,
                           json={"content": doc.content + "\n\nUpdated wall-port labels for floor 4."})
    assert r.status_code == 200 and r.json()["last_reviewed"] == date.today().isoformat()
    await client.patch(f"/api/v1/knowledge/documents/{doc.id}", headers=support, json={"content": doc.content})


@pytest.mark.parametrize("row", SOLUTIONS_SPEC, ids=lambda r: r["kb"] + ":" + r["intent"])
async def test_verified_solution_is_reusable_without_llm(db, row):
    cat = (await db.execute(select(TicketCategory).where(TicketCategory.name == row["category"]))).unique().scalar_one()
    r = await retrieve(db, row["problem"], category_id=cat.id, intent=row["intent"])
    hit = next((h for h in r.solutions if h.solution.title == row["title"]), None)
    assert hit is not None, f"{row['title']} not retrieved for its own problem text"
    assert hit.reusable_without_llm and hit.solution.confidence_level in (
        SolutionConfidence.HUMAN_VERIFIED, SolutionConfidence.ADMIN_VERIFIED)
    assert (PROJECT_DIR / "data" / "knowledge" / f"{row['kb']}.md").exists()


async def test_symptoms_match_presents_the_documents_procedure(db):
    symptoms = (await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.heading == "Symptoms"))).unique().scalars().first()
    proc = await procedure_for(db, ChunkHit(symptoms, 0.71))
    assert proc is not None and proc.chunk.document_id == symptoms.document_id
    assert proc.chunk.heading.startswith("Resolution") and proc.similarity == 0.71
    escalation = (await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.heading == "Escalation criteria"))).unique().scalars().first()
    assert (await procedure_for(db, ChunkHit(escalation, 0.6))).chunk.heading.startswith("Resolution")


async def test_kb_procedure_shown_to_employee_is_a_resolution(client):
    from tests.conftest import chat_until_ticket

    h, _ = await new_employee(client)
    reply = await chat_until_ticket(client, h, "Prints from the floor printer come out with vertical streaks and faded areas",
                                    ["Paper jam / error light", "Just me"])
    sol = reply["payload"]["solution"]
    assert sol and sol["steps"]
    assert not any(s.startswith(("The printer panel shows", "Prints have")) for s in sol["steps"])  # not the symptom list


async def test_faiss_indexes_rebuild_from_the_database(db, tmp_path):
    mgr = IndexManager(str(tmp_path / "rebuild"))
    report = await mgr.rebuild_all(db)
    chunks = {c.id for c in (await db.execute(select(KnowledgeChunk))).unique().scalars()}
    verified = {s.id for s in (await db.execute(select(TicketSolution).where(
        TicketSolution.confidence_level.in_(SolutionConfidence.REUSABLE), TicketSolution.is_active.is_(True),
        TicketSolution.rejected.is_(False)))).unique().scalars()}
    assert mgr.stores[KNOWLEDGE].ids() == chunks and report[KNOWLEDGE]["count"] == len(chunks)
    assert mgr.stores[SOLUTIONS].ids() == verified and len(verified) >= len(SOLUTIONS_SPEC)
    assert report[TICKETS]["count"] == len(mgr.stores[TICKETS].ids())
    loaded = await IndexManager(str(tmp_path / "rebuild")).initialize(db)
    assert all(v["action"] == "loaded" for v in loaded.values())


def _shingles(text: str, n: int = 8) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def test_seed_data_and_tests_do_not_reuse_evaluation_text():
    """The paper reports that the held-out evaluation set is not used by seed data, the KB or the tests."""
    data = json.loads((PROJECT_DIR / "data" / "eval" / "eval_set.json").read_text(encoding="utf-8"))
    texts = [r["text"] for r in data["classification"]] + [p[k] for p in data["duplicate_pairs"] for k in ("a", "b")]
    held_out = set().union(*(_shingles(t) for t in texts))
    sources = [*KB, *(PROJECT_DIR / "data" / "seed").glob("*.json"), *(PROJECT_DIR / "backend" / "tests").glob("*.py"),
               *(PROJECT_DIR / "backend" / "app" / "database").glob("*.py")]
    leaks = {str(p.relative_to(PROJECT_DIR)): sorted(_shingles(p.read_text(encoding="utf-8")) & held_out)[:2]
             for p in sources if _shingles(p.read_text(encoding="utf-8")) & held_out}
    assert not leaks, leaks
