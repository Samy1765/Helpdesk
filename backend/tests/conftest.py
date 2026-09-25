"""
Test fixtures: an isolated SQLite database and FAISS directory per test session, real
sentence-transformer embeddings (so semantic tests are meaningful), LLMs disabled (the system
must work without them) and network diagnostics disabled.
"""

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="precision_ai_tests_"))
# Default: throwaway SQLite file. Set TEST_DATABASE_URL to run the same suite against PostgreSQL
# (the database is wiped at session start).
os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{(TMP / 'test.db').as_posix()}",
    "FAISS_INDEX_DIR": str(TMP / "faiss"),
    "UPLOAD_DIR": str(TMP / "uploads"),
    "LLM_SMALL_PROVIDER": "none",
    "LLM_LARGE_PROVIDER": "none",
    "AGENT_TOOLS_ENABLED": "false",
    "SERVE_FRONTEND": "false",
    "LOG_LEVEL": "WARNING",
    "EMBEDDING_BACKEND": "sentence-transformers",
})

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.database import async_session_factory  # noqa: E402
from app.database.session import create_all_tables  # noqa: E402
from app.vector_store import IndexManager, get_index_manager, set_index_manager  # noqa: E402

_counter = {"n": 0}


@pytest_asyncio.fixture(scope="session", autouse=True)
async def seeded_db():
    from app.database.seed import seed_history, seed_knowledge, seed_reference

    if os.environ.get("TEST_DATABASE_URL"):
        from app.database import Base, engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    await create_all_tables()
    set_index_manager(IndexManager(str(TMP / "faiss")))
    async with async_session_factory() as db:
        ref = await seed_reference(db)
        await db.commit()
        await seed_knowledge(db, ref["categories"], ref["users"]["admin"])
        await seed_history(db, ref)
        await db.commit()
        await get_index_manager().initialize(db)
    yield


@pytest_asyncio.fixture
async def db():
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def login(client: AsyncClient, username: str, password: str) -> dict:
    r = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def new_employee(client: AsyncClient, prefix: str = "emp") -> tuple[dict, dict]:
    """Register a fresh employee so tests do not interfere with each other."""
    _counter["n"] += 1
    uname = f"{prefix}{_counter['n']}_{os.getpid()}"
    r = await client.post("/api/v1/auth/register", json={
        "email": f"{uname}@example.com", "username": uname, "password": "Passw0rd!x", "full_name": f"Test {uname}"})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]


async def chat_until_ticket(client: AsyncClient, headers: dict, message: str, answers: list[str] | None = None,
                            user_priority: str | None = None) -> dict:
    """Send an issue and answer clarifying questions until the ticket is generated."""
    await client.post("/api/v1/chat/new", headers=headers)
    body = {"message": message}
    if user_priority:
        body["user_priority"] = user_priority
    r = await client.post("/api/v1/chat/message", headers=headers, json=body)
    assert r.status_code == 200, r.text
    reply = r.json()
    answers = list(answers or [])
    for _ in range(4):
        if reply["stage"] != "clarifying":
            break
        answer = answers.pop(0) if answers else reply["quick_replies"][0]
        r = await client.post("/api/v1/chat/message", headers=headers, json={"message": answer})
        assert r.status_code == 200, r.text
        reply = r.json()
    assert reply["ticket_id"], reply
    return reply
