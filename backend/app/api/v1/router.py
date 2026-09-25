"""
Precision AI - API v1 router.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import actions, admin, auth, chat, incidents, knowledge, meta, support, tickets

api_router = APIRouter(prefix="/api/v1")
for module in (auth, chat, tickets, actions, incidents, knowledge, support, admin, meta):
    api_router.include_router(module.router)
