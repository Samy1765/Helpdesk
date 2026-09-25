"""
Precision AI - Agent action approvals (human-in-the-loop for restricted / dangerous tools).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import troubleshooting_agent as agent
from app.core.deps import get_current_user, is_staff
from app.database import get_db
from app.models.agent import AgentAction
from app.models.conversation import Conversation
from app.models.ticket import Ticket
from app.models.user import User
from app.services import tickets as ticket_svc
from app.tools.executor import PermissionDenied, action_view, can_decide, decide

router = APIRouter(prefix="/actions", tags=["Agent actions"])


class DecisionIn(BaseModel):
    approve: bool


@router.get("/pending")
async def pending(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    q = select(AgentAction).where(AgentAction.status == "pending_approval")
    if not is_staff(user):
        q = q.join(Ticket, AgentAction.ticket_id == Ticket.id).where(Ticket.user_id == user.id)
    rows = (await db.execute(q.order_by(AgentAction.id.desc()))).unique().scalars().all()
    return [{**action_view(a), "ticket_id": a.ticket_id, "ticket_number": a.ticket.ticket_number,
             "ticket_title": a.ticket.title, "can_decide": can_decide(a, user)} for a in rows]


@router.post("/{action_id}/decision")
async def decision(action_id: int, data: DecisionIn, db: AsyncSession = Depends(get_db),
                   user: User = Depends(get_current_user)):
    action = (await db.execute(select(AgentAction).where(AgentAction.id == action_id))).unique().scalar_one_or_none()
    if action is None or (not is_staff(user) and action.ticket.user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action not found")
    try:
        await decide(db, action, user, data.approve)
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    await ticket_svc.audit(db, "action_approved" if data.approve else "action_rejected", user_id=user.id,
                           resource_type="agent_action", resource_id=action.id,
                           details={"tool": action.tool_name, "ticket_id": action.ticket_id})
    outcome = await agent.after_action_decision(db, action)
    conv_id = (await db.execute(select(Conversation.id).where(Conversation.ticket_id == action.ticket_id))).scalar()
    await ticket_svc.add_message(db, role="assistant", content=outcome.message, ticket_id=action.ticket_id,
                                 conversation_id=conv_id,
                                 payload={**outcome.payload, "quick_replies": outcome.quick_replies})
    return {"action": action_view(action), "message": outcome.message, "payload": outcome.payload,
            "quick_replies": outcome.quick_replies}
