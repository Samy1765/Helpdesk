"""Demo company seed (SEED_DEMO_DATA) end to end on a throwaway database, plus the ratings and quarterly analytics
that the demo data feeds."""

import os
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.core.config import BACKEND_DIR
from tests.conftest import chat_until_ticket, login, new_employee

API = "/api/v1"
SLA = {"critical": 60, "high": 240, "medium": 480, "low": 1440}


def _run(args: list[str], env: dict) -> str:
    r = subprocess.run([sys.executable, *args], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-4000:]
    return r.stdout


@pytest.fixture(scope="module")
def demo_db(tmp_path_factory) -> tuple[Path, str, str]:
    tmp = tmp_path_factory.mktemp("demo")
    env = {**os.environ, "APP_ENV": "test", "DATABASE_URL": f"sqlite+aiosqlite:///{(tmp / 'demo.db').as_posix()}",
           "FAISS_INDEX_DIR": str(tmp / "faiss"), "EMBEDDING_BACKEND": "hashing", "LLM_SMALL_PROVIDER": "none",
           "LLM_LARGE_PROVIDER": "none", "AGENT_TOOLS_ENABLED": "false", "LOG_LEVEL": "WARNING", "SEED_DEMO_DATA": "true"}
    env.pop("TEST_DATABASE_URL", None)
    _run(["-m", "alembic", "upgrade", "head"], env)
    first = _run(["-m", "app.database.seed", "--no-simulate"], env)
    second = _run(["-m", "app.database.seed", "--no-simulate"], env)
    return tmp / "demo.db", first, second


def _q(db: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value[:19])


def test_demo_company_people_and_departments(demo_db):
    db, first, _ = demo_db
    roles = dict(_q(db, "select r.name, count(*) from users u join roles r on r.id=u.role_id where u.is_active group by 1"))
    assert 55 <= roles["employee"] <= 65 and 10 <= roles["it_support"] <= 12 and 1 <= roles["admin"] <= 2
    units = _q(db, "select count(distinct d.id) from users u join departments d on d.id=u.department_id "
                   "join roles r on r.id=u.role_id where r.name='employee' and u.is_active and not d.is_support_team")
    assert units[0][0] == 15
    assert all(e.endswith("@acme-demo.in") for (e,) in _q(db, "select email from users"))
    assert _q(db, "select count(*) from users where not is_active")[0][0] >= 1  # a leaver keeps the history real
    for account in ("admin", "itsupport", "johndoe", "it.manager", "desk2.agent"):
        assert account in first  # demo sign-ins are printed at the end of seeding


def test_demo_quarter_of_tickets(demo_db):
    db, _, _ = demo_db
    tickets = _q(db, "select ticket_number, created_at, status, priority, resolved_at from tickets order by created_at")
    assert 300 <= len(tickets) <= 400
    first, last = _ts(tickets[0][1]), _ts(tickets[-1][1])
    assert timedelta(days=80) <= last - first <= timedelta(days=91)
    numbers = [int(t[0][4:]) for t in tickets]
    assert numbers == sorted(numbers)  # INC numbers follow creation order
    cats = {c for (c,) in _q(db, "select distinct tc.name from tickets t join ticket_categories tc on tc.id=t.category_id")}
    assert len(cats) == 10
    # arrival pattern of everyday tickets (incident bursts and the older fixed history excluded)
    everyday = [_ts(c) + timedelta(hours=5, minutes=30) for (c,) in _q(
        db, "select created_at from tickets where incident_id is null and source != 'historical_import'")]
    weekdays = Counter(t.weekday() for t in everyday)
    assert weekdays[0] > weekdays[2] > weekdays[5]  # Monday spike, quiet Saturday
    assert sum(1 for t in everyday if 9 <= t.hour < 19) / len(everyday) > 0.8  # office hours (IST)
    statuses = Counter(t[2] for t in tickets)
    for s in ("resolved", "closed", "duplicate", "awaiting_user"):
        assert statuses[s] > 0, s
    assert statuses["escalated"] + statuses["assigned"] + statuses["in_progress"] >= 5
    resolved = [t for t in tickets if t[4] and t[2] in ("resolved", "closed")]
    met = sum(1 for t in resolved if (_ts(t[4]) - _ts(t[1])).total_seconds() / 60 <= SLA[t[3]])
    assert 0.75 < met / len(resolved) < 0.98  # mostly within SLA, some breaches


def test_demo_incidents_approvals_feedback_and_knowledge(demo_db):
    db, _, _ = demo_db
    incidents = _q(db, "select incident_number, status, (select count(*) from tickets t where t.incident_id=i.id) from incidents i")
    assert len(incidents) >= 3 and all(s == "resolved" and n >= 5 for _, s, n in incidents)
    assert {"INCIDENT-EMAIL-001", "INCIDENT-VPN-001"} <= {n for n, _, _ in incidents}
    actions = dict(_q(db, "select status, count(*) from agent_actions where approval_required group by 1"))
    assert actions["approved"] > 0 and actions["rejected"] > 0 and actions["pending_approval"] >= 3
    ratings = [r for (r,) in _q(db, "select satisfaction_rating from ticket_feedback where satisfaction_rating is not null")]
    assert len(ratings) > 100 and 4.0 <= sum(ratings) / len(ratings) <= 4.8
    routing = dict(_q(db, "select routing_level, count(*) from agent_runs group by 1"))
    assert routing["L3_verified_retrieval"] > routing["L0_policy"] > 0 and routing["L2_similarity"] > 0
    assert _q(db, "select count(*) from llm_usage_log")[0][0] == 0  # no fabricated model usage
    assert _q(db, "select count(*) from knowledge_documents")[0][0] >= 40


def test_demo_seed_is_idempotent(demo_db):
    db, _, second = demo_db
    assert "already present" in second and "Historical tickets added: 0" in second
    assert _q(db, "select count(*) from audit_logs where action='demo_company_seeded'")[0][0] == 1
    from app.vector_store.faiss_store import FaissVectorStore

    store = FaissVectorStore("tickets", 768, str(db.parent / "faiss"), "hashing:768")
    assert store.load()  # the index was rebuilt from the database after seeding
    assert store.ids() == {r[0] for r in _q(db, "select id from tickets")}


# ---------------------------------------------------------------- ratings and analytics
async def test_requester_rates_resolved_ticket(client):
    h, _ = await new_employee(client)
    reply = await chat_until_ticket(client, h, "VPN keeps timing out on login right after I enter the 2FA code", ["Just me"])
    tid = reply["ticket_id"]
    assert (await client.post(f"{API}/tickets/{tid}/rating", headers=h, json={"rating": 5})).status_code == 409  # still open
    await client.post(f"{API}/chat/message", headers=h, json={"message": "Yes, it's fixed"})
    assert (await client.post(f"{API}/tickets/{tid}/rating", headers=h, json={"rating": 6})).status_code == 422
    assert (await client.post(f"{API}/tickets/{tid}/rating", headers=h, json={"rating": 3})).status_code == 200
    r = await client.post(f"{API}/tickets/{tid}/rating", headers=h, json={"rating": 4, "comment": "Quick fix, thanks"})
    assert r.status_code == 200
    assert (await client.get(f"{API}/tickets/{tid}", headers=h)).json()["rating"] == 4  # replaced, not added
    other, _ = await new_employee(client)
    assert (await client.post(f"{API}/tickets/{tid}/rating", headers=other, json={"rating": 1})).status_code == 404
    support = await login(client, "itsupport", "Support@123")
    assert (await client.post(f"{API}/tickets/{tid}/rating", headers=support, json={"rating": 1})).status_code == 403


async def test_admin_analytics_include_sla_satisfaction_and_approvals(client):
    admin = await login(client, "admin", "Admin@123")
    a = (await client.get(f"{API}/admin/analytics?days=90", headers=admin)).json()
    assert {"compliance", "met", "breached", "open_breached", "by_priority"} <= set(a["sla"])
    assert [p["name"] for p in a["sla"]["by_priority"]] == ["critical", "high", "medium", "low"]
    assert a["sla"]["met"] + a["sla"]["breached"] == sum(p["met"] + p["breached"] for p in a["sla"]["by_priority"])
    assert [d["name"] for d in a["satisfaction"]["distribution"]] == ["5", "4", "3", "2", "1"]
    assert a["satisfaction"]["rated"] >= 1 and 1 <= a["satisfaction"]["average_rating"] <= 5
    assert set(a["approvals"]) == {"approved", "rejected", "pending"}
    support = await login(client, "itsupport", "Support@123")
    assert "sla_breached_open" in (await client.get(f"{API}/support/overview", headers=support)).json()
