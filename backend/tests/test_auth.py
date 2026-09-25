"""Authentication, password hashing and role-based access."""

from sqlalchemy import select

from app.core.security import create_refresh_token, hash_password, verify_password
from app.models import User
from tests.conftest import login, new_employee


def test_password_hashing_never_plaintext():
    h = hash_password("S3cret!pass")
    assert h != "S3cret!pass" and h.startswith("$2")
    assert verify_password("S3cret!pass", h)
    assert not verify_password("wrong", h)


async def test_register_login_me(client, db):
    headers, user = await new_employee(client)
    assert user["role"] == "employee"
    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200 and r.json()["username"] == user["username"]
    stored = (await db.execute(select(User).where(User.id == user["id"]))).unique().scalar_one()
    assert stored.password_hash != "Passw0rd!x"
    assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 200


async def test_login_by_email_and_bad_password(client):
    _, user = await new_employee(client)
    ok = await client.post("/api/v1/auth/login", json={"username": user["email"], "password": "Passw0rd!x"})
    assert ok.status_code == 200
    bad = await client.post("/api/v1/auth/login", json={"username": user["username"], "password": "nope"})
    assert bad.status_code == 401


async def test_duplicate_and_weak_registration(client):
    _, user = await new_employee(client)
    dup = await client.post("/api/v1/auth/register", json={
        "email": user["email"], "username": "someoneelse", "password": "Passw0rd!x", "full_name": "X Y"})
    assert dup.status_code == 409
    weak = await client.post("/api/v1/auth/register", json={
        "email": "weak@example.com", "username": "weakpw", "password": "alllowercase", "full_name": "Weak"})
    assert weak.status_code == 422


async def test_self_registration_cannot_choose_role(client):
    r = await client.post("/api/v1/auth/register", json={
        "email": "sneaky@example.com", "username": "sneaky", "password": "Passw0rd!x", "full_name": "Sneaky",
        "role": "admin"})
    assert r.status_code == 201 and r.json()["user"]["role"] == "employee"


async def test_role_based_access(client):
    emp, _ = await new_employee(client)
    assert (await client.get("/api/v1/admin/analytics", headers=emp)).status_code == 403
    assert (await client.get("/api/v1/support/queue", headers=emp)).status_code == 403
    support = await login(client, "itsupport", "Support@123")
    assert (await client.get("/api/v1/support/queue", headers=support)).status_code == 200
    assert (await client.get("/api/v1/admin/analytics", headers=support)).status_code == 403
    admin = await login(client, "admin", "Admin@123")
    assert (await client.get("/api/v1/admin/analytics", headers=admin)).status_code == 200


async def test_refresh_token_flow_and_type_enforced(client):
    r = await client.post("/api/v1/auth/login", json={"username": "johndoe", "password": "Employee@123"})
    tokens = r.json()
    # a refresh token must not work as an access token
    bad = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert bad.status_code == 401
    new = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert new.status_code == 200 and new.json()["access_token"]
    forged = create_refresh_token({"sub": "999999"})
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": forged})).status_code == 401


async def test_unauthenticated_requests_rejected(client):
    assert (await client.get("/api/v1/tickets")).status_code == 401
    assert (await client.get("/api/v1/tickets", headers={"Authorization": "Bearer garbage"})).status_code == 401
