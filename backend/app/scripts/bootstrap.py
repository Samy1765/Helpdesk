"""
Precision AI - production bootstrap (no demo data).

Creates roles, support teams, categories and the IT knowledge base, then an administrator from
environment variables (only if that username does not exist yet):

  BOOTSTRAP_ADMIN_USERNAME=admin BOOTSTRAP_ADMIN_EMAIL=it-admin@yourco.com \
  BOOTSTRAP_ADMIN_PASSWORD='<strong password>' python -m app.scripts.bootstrap
"""

import asyncio
import os
import re

from sqlalchemy import select

from app.core.logging import setup_logging
from app.core.security import hash_password
from app.database import async_session_factory
from app.database.seed import seed_knowledge, seed_reference
from app.models import Role, User
from app.vector_store import get_index_manager


async def main() -> None:
    setup_logging()
    async with async_session_factory() as db:
        ref = await seed_reference(db, demo_users=False)
        await db.commit()
        username = os.environ.get("BOOTSTRAP_ADMIN_USERNAME")
        admin = None
        if username:
            admin = (await db.execute(select(User).where(User.username == username))).unique().scalar_one_or_none()
            if admin is None:
                password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
                if len(password) < 12 or not (re.search(r"[A-Z]", password) and re.search(r"\d", password)):
                    raise SystemExit("BOOTSTRAP_ADMIN_PASSWORD must be 12+ chars with an upper-case letter and a digit")
                role = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one()
                admin = User(username=username.lower(), email=os.environ.get("BOOTSTRAP_ADMIN_EMAIL", f"{username}@example.com"),
                             full_name=os.environ.get("BOOTSTRAP_ADMIN_NAME", "IT Administrator"), role=role,
                             department=ref["departments"]["SERVICE_DESK"], password_hash=hash_password(password))
                db.add(admin)
                await db.flush()
                print(f"Created administrator '{username}'")
        docs = await seed_knowledge(db, ref["categories"], admin)
        await db.commit()
        await get_index_manager().rebuild_all(db)
    print(f"Bootstrap complete (knowledge documents added: {docs}).")


if __name__ == "__main__":
    asyncio.run(main())
