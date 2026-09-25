"""
Precision AI - Tool execution with permission enforcement and human approval.

SAFE tools execute immediately. RESTRICTED and DANGEROUS tools create a pending AgentAction
that must be approved by the right person before anything runs:
  restricted -> the ticket's requester (consent on their own device/account) or IT staff
  dangerous  -> administrators only
State-changing actions run through an ActionConnector. The default connector is a dry run
that records the action for IT follow-up; wire a real endpoint-management / identity
connector in `get_connector()` for production.
"""

import time
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database import utcnow
from app.models.agent import AgentAction, AgentRun
from app.models.ticket import Ticket
from app.models.user import User
from app.tools.registry import DANGEROUS, RESTRICTED, SAFE, ToolSpec, get_tool

logger = get_logger(__name__)


class PermissionDenied(Exception):
    pass


class ActionConnector(ABC):
    mode: str

    @abstractmethod
    async def execute(self, tool: ToolSpec, params: dict, ticket: Ticket) -> dict: ...


class DryRunConnector(ActionConnector):
    """Records the approved action; no remote system is modified."""
    mode = "dry_run"

    async def execute(self, tool: ToolSpec, params: dict, ticket: Ticket) -> dict:
        return {"ok": True, "mode": self.mode, "executed": False,
                "summary": f"{tool.label} approved and queued for {ticket.ticket_number} "
                           f"(dry-run: no endpoint-management connector configured)"}


def get_connector() -> ActionConnector:
    return DryRunConnector()


async def run_tool(db: AsyncSession, run: AgentRun, ticket: Ticket, tool_name: str, params: dict) -> AgentAction:
    spec = get_tool(tool_name)
    action = AgentAction(agent_run_id=run.id, ticket_id=ticket.id, tool_name=tool_name,
                         permission_level=spec.permission if spec else DANGEROUS, parameters=params)
    if spec is None:
        action.status, action.result = "blocked", {"ok": False, "summary": "Tool is not registered; blocked"}
        logger.warning("tool_blocked_unregistered", tool=tool_name, ticket_id=ticket.id, agent_run_id=run.id)
    elif spec.permission == SAFE:
        await _execute_safe(spec, params, action)
    else:
        action.status = "pending_approval"
        action.approval_required = True
        action.approver_role = spec.approver_role
        action.result = {"summary": f"Awaiting approval ({spec.permission})"}
    db.add(action)
    await db.flush()
    logger.info("tool_invoked", tool=tool_name, permission=action.permission_level, status=action.status,
                ticket_id=ticket.id, agent_run_id=run.id, latency_ms=action.latency_ms)
    return action


async def _execute_safe(spec: ToolSpec, params: dict, action: AgentAction) -> None:
    if not get_settings().AGENT_TOOLS_ENABLED:
        action.status, action.result = "skipped", {"ok": None, "summary": "Diagnostics disabled by configuration"}
        return
    start = time.perf_counter()
    try:
        action.result = await spec.handler(params)  # type: ignore[misc]
        action.status = "executed"
    except (ValueError, KeyError) as exc:
        action.status, action.result = "failed", {"ok": False, "summary": f"Invalid parameters: {exc}"}
    except Exception as exc:  # a diagnostic must never crash the agent
        action.status, action.result = "failed", {"ok": False, "summary": f"{type(exc).__name__}"}
    action.latency_ms = round((time.perf_counter() - start) * 1000, 1)


def can_decide(action: AgentAction, user: User) -> bool:
    role = user.role_name
    if action.permission_level == DANGEROUS:
        return role == "admin"
    if action.permission_level == RESTRICTED:
        return role in ("admin", "it_support") or action.ticket.user_id == user.id
    return False


async def decide(db: AsyncSession, action: AgentAction, user: User, approve: bool) -> AgentAction:
    if action.status != "pending_approval":
        raise ValueError("Action is not awaiting approval")
    if not can_decide(action, user):
        raise PermissionDenied("You are not allowed to approve this action")
    action.approved_by = user.id
    action.decided_at = utcnow()
    if not approve:
        action.status = "rejected"
        action.result = {"ok": None, "summary": f"Rejected by {user.full_name}"}
    else:
        spec = get_tool(action.tool_name)
        if spec is None:
            raise ValueError("Tool is no longer registered")
        start = time.perf_counter()
        action.result = await get_connector().execute(spec, action.parameters or {}, action.ticket)
        action.latency_ms = round((time.perf_counter() - start) * 1000, 1)
        action.status = "approved"
    await db.flush()
    logger.info("tool_decision", tool=action.tool_name, approve=approve, by=user.id, ticket_id=action.ticket_id)
    return action


def action_view(action: AgentAction) -> dict:
    spec = get_tool(action.tool_name)
    return {
        "id": action.id, "tool": action.tool_name, "label": spec.label if spec else action.tool_name,
        "description": spec.description if spec else "", "permission": action.permission_level,
        "risk_note": spec.risk_note if spec else "", "status": action.status,
        "approver_role": action.approver_role, "result": action.result or {},
        "created_at": action.created_at.isoformat() if action.created_at else None,
    }

