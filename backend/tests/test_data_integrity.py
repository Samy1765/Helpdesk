"""Seed and knowledge data must stay independent of the held-out evaluation set, and every
runbook must carry the metadata the loader and the UI rely on."""

import json
import re

from app.core.config import PROJECT_DIR
from app.database.seed import CATEGORY_DEPARTMENT, parse_front_matter

DATA = PROJECT_DIR / "data"
# Eight-word windows catch a reused or lightly edited sentence without flagging short generic
# phrases such as "connected but no internet" that any IT text contains.
SHINGLE = 8


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _shingles(text: str) -> set[tuple[str, ...]]:
    w = _words(text)
    return {tuple(w[i:i + SHINGLE]) for i in range(len(w) - SHINGLE + 1)}


def _eval_texts() -> list[str]:
    data = json.loads((DATA / "eval" / "eval_set.json").read_text(encoding="utf-8"))
    texts = [r["text"] for r in data["classification"]]
    texts += [p[k] for p in data["duplicate_pairs"] for k in ("a", "b")]
    return texts


def _corpus() -> dict[str, str]:
    files = sorted((DATA / "knowledge").glob("*.md")) + sorted((DATA / "seed").glob("*.json"))
    files.append(PROJECT_DIR / "backend" / "app" / "database" / "demo_data.py")
    return {f.name: f.read_text(encoding="utf-8") for f in files}


def test_no_evaluation_text_in_seed_knowledge_or_demo_data():
    corpus = {name: _shingles(text) for name, text in _corpus().items()}
    leaks = []
    for text in _eval_texts():
        sh = _shingles(text)
        for name, cs in corpus.items():
            if sh & cs:
                leaks.append((name, text))
    assert not leaks, f"evaluation sentences reused in seed/knowledge data: {leaks[:5]}"


def test_runbooks_have_valid_metadata_and_steps():
    paths = sorted((DATA / "knowledge").glob("*.md"))
    assert len(paths) >= 40
    seen_categories = set()
    for path in paths:
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        assert meta.get("title"), path.name
        assert meta.get("category") in CATEGORY_DEPARTMENT, path.name
        seen_categories.add(meta["category"])
        assert re.search(r"^\d+\. ", body, re.M), f"{path.name} has no numbered steps"
    assert seen_categories == set(CATEGORY_DEPARTMENT)


async def test_demo_organisation_is_consistent(tmp_path):
    """Seed the 90-day demo organisation into its own database (the shared test DB stays untouched)."""
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.database import Base
    from app.database.demo_data import seed_demo_org
    from app.database.seed import seed_history, seed_knowledge, seed_reference
    from app.models import Incident, Ticket, TicketStatus, User

    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'demo.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        ref = await seed_reference(db)
        await seed_knowledge(db, ref["categories"], ref["users"]["admin"])
        await seed_history(db, ref)
        counts = await seed_demo_org(db, ref)
        await db.commit()
        assert counts["employees_added"] == 45 and counts["incidents"] == 4 and counts["verified_fixes"] >= 10
        assert counts["resolved_by_assistant"] > 50 and counts["resolved_by_it"] > 50

        tickets = (await db.execute(select(Ticket).order_by(Ticket.created_at, Ticket.id))).unique().scalars().all()
        assert len(tickets) > 300
        assert [t.ticket_number for t in tickets] == [f"INC-{i:06d}" for i in range(1, len(tickets) + 1)]
        for t in tickets:
            if t.status == TicketStatus.RESOLVED:
                assert t.resolved_at is not None and t.resolved_at >= t.created_at, t.ticket_number
        assert (await db.execute(select(func.count(Incident.id)).where(Incident.status == "resolved"))).scalar() == 4
        emails = (await db.execute(select(User.email))).scalars().all()
        assert all(e.endswith("@example.com") for e in emails)
        assert await seed_demo_org(db, ref) == {}  # idempotent
    await engine.dispose()
