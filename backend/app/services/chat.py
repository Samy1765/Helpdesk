"""
Precision AI - Chat service (the employee's front door).

Conversation stages (persisted in `conversations`):
  intake      -> the employee describes the issue; we classify it (rules first)
  clarifying  -> at most two targeted follow-up questions (symptom, scope) with quick replies
  agent       -> ticket generated; the troubleshooting agent drives the conversation
  closed      -> terminal (resolved / escalated / duplicate / incident); next message starts fresh

The structured ticket is validated by `TicketDraft` (pydantic) before anything is written.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import troubleshooting_agent as agent
from app.agents.state_machine import AgentState
from app.core.logging import get_logger
from app.models.conversation import Conversation
from app.models.ticket import TicketMessage
from app.models.user import User
from app.services import classification as cls_svc, priority as prio_svc, tickets as ticket_svc
from app.services.priority import LEVELS, detect_scope
from app.vector_store import get_index_manager

logger = get_logger(__name__)

GENERIC_INTENTS = {None, "vpn_connection_failure", "email_access_failure", "printer_not_printing",
                   "software_crash", "laptop_hardware_failure", "server_performance", "database_access",
                   "network_outage", "password_reset"}

SYMPTOM_QUESTIONS: dict[str, tuple[str, list[str]]] = {
    "VPN": ("I can help with that. Does the VPN fail immediately, or does it connect and then disconnect?",
            ["Fails instantly on MFA / login", "Connects then drops out", "Shows an error code", "Can't reach the gateway at all"]),
    "Network": ("Is this on Wi-Fi, a wired connection, or both - and do other devices on the same network work?",
                ["Wi-Fi only", "Wired only", "Nothing connects at all", "Connected but very slow"]),
    "Password": ("Which of these best describes what happens when you try to sign in?",
                 ["My account is locked", "I forgot my password", "My password expired", "MFA / authenticator problem"]),
    "Email": ("What happens when you try to use email?",
              ["Outlook crashes or won't open", "Can't send or receive mail", "Web mail fails too", "Calendar / Teams not syncing"]),
    "Printer": ("What happens when you try to print?",
                ["Jobs stuck in the queue", "Paper jam / error light", "Printer shows offline", "Need to add a printer"]),
    "Hardware": ("What's happening with the device?",
                 ["Won't power on or charge", "Screen / display problem", "Keyboard, mouse or dock", "Physically damaged"]),
    "Software": ("What happens with the application?",
                 ["It crashes or freezes", "It won't install / update", "License or activation error", "I need new software"]),
    "Security": ("Thanks for reporting this - please don't click any more links. What did you notice?",
                 ["Suspicious email, I didn't click", "I clicked a link / entered my password", "Pop-ups or strange behaviour", "Unknown sign-in alert"]),
    "Server": ("Which server or service is affected, and what do users see?",
               ["It's completely down", "Very slow responses", "HTTP 500 / 503 errors", "Disk space alerts"]),
    "Database": ("Which database or application is it, and what do you see?",
                 ["Can't connect / log in", "Queries slow or timing out", "Database appears down", "Permission denied"]),
}
DEFAULT_SYMPTOM = ("Could you tell me a bit more - what were you trying to do, and what happened instead "
                   "(including any error message)?", [])
SCOPE_QUESTION = ("Is anyone else affected?", ["Just me", "A few colleagues", "My whole team / department",
                                               "Everyone in the company"])

GREETING = re.compile(r"^\s*(hi|hello|hey|good (morning|afternoon|evening)|hiya|help|yo)\W*$", re.I)
YES = re.compile(r"^\s*(yes|yep|yeah|y|ok it works|it works|worked|fixed|resolved|solved|that (did it|worked|fixed it)|all good|it'?s fixed)\b", re.I)
NO = re.compile(r"^\s*(no|nope|nah|n|still|didn'?t|doesn'?t|not (working|fixed|resolved)|it'?s still|same (issue|problem))\b", re.I)


class TicketDraft(BaseModel):
    """Strict schema for the structured ticket generated from the conversation."""
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=5, max_length=8000)
    category: str
    category_id: int
    sub_category: Optional[str] = Field(default=None, max_length=100)
    intent: Optional[str] = Field(default=None, max_length=120)
    entities: dict[str, str] = Field(default_factory=dict)
    ai_confidence: float = Field(ge=0, le=1)
    classification_method: str
    user_priority: Optional[str] = None
    system_priority: str
    priority_confidence: float = Field(ge=0, le=1)
    priority_reason: str
    priority_impact: str
    priority_urgency: str

    @field_validator("user_priority", "system_priority")
    @classmethod
    def valid_priority(cls, v):
        if v is not None and v not in LEVELS:
            raise ValueError("invalid priority")
        return v


@dataclass
class ChatReply:
    conversation_id: int
    message: str
    stage: str
    payload: dict = field(default_factory=dict)
    quick_replies: list[str] = field(default_factory=list)
    ticket_id: Optional[int] = None
    ticket_number: Optional[str] = None
    message_id: Optional[int] = None


# ------------------------------------------------------------------ conversation helpers
async def get_active_conversation(db: AsyncSession, user: User, create: bool = True) -> Optional[Conversation]:
    conv = (await db.execute(select(Conversation).where(Conversation.user_id == user.id,
                                                        Conversation.status == "active")
                             .order_by(Conversation.id.desc()).limit(1))).unique().scalar_one_or_none()
    if conv is None and create:
        conv = Conversation(user_id=user.id, stage="intake", status="active", slots={})
        db.add(conv)
        await db.flush()
    return conv


async def close_conversation(db: AsyncSession, conv: Conversation) -> None:
    conv.status, conv.stage = "closed", "closed"


async def history(db: AsyncSession, conv: Conversation) -> list[TicketMessage]:
    return list((await db.execute(select(TicketMessage).where(TicketMessage.conversation_id == conv.id,
                                                              TicketMessage.is_internal.is_(False))
                                  .order_by(TicketMessage.id))).unique().scalars().all())


async def _reply(db: AsyncSession, conv: Conversation, text: str, *, payload: Optional[dict] = None,
                 quick_replies: Optional[list[str]] = None) -> ChatReply:
    payload = {**(payload or {}), "quick_replies": quick_replies or []}
    msg = await ticket_svc.add_message(db, role="assistant", content=text, conversation_id=conv.id,
                                       ticket_id=conv.ticket_id, payload=payload)
    ticket = conv.ticket
    return ChatReply(conversation_id=conv.id, message=text, stage=conv.stage, payload=payload,
                     quick_replies=quick_replies or [], ticket_id=conv.ticket_id,
                     ticket_number=ticket.ticket_number if ticket else None, message_id=msg.id)


def _slots(conv: Conversation) -> dict:
    return dict(conv.slots or {})


# ------------------------------------------------------------------ main entry
async def handle_message(db: AsyncSession, user: User, text: str, *, user_priority: Optional[str] = None,
                         client_env: Optional[dict] = None, attachments: Optional[list[dict]] = None) -> ChatReply:
    text = text.strip()
    conv = await get_active_conversation(db, user)
    assert conv is not None

    # A finished conversation never absorbs a new issue: start a fresh one
    if conv.stage == "agent" and conv.ticket_id:
        run = await agent.active_run(db, conv.ticket_id)
        if run is None or run.state != AgentState.VERIFY.value:
            await close_conversation(db, conv)
            conv = await get_active_conversation(db, user)
            assert conv is not None

    await ticket_svc.add_message(db, role="user", content=text, conversation_id=conv.id, ticket_id=conv.ticket_id,
                                 user_id=user.id, payload={"attachments": attachments or [],
                                                           "user_priority": user_priority})

    if conv.stage == "agent":
        return await _handle_agent_stage(db, user, conv, text, user_priority, client_env)
    if conv.stage == "clarifying":
        return await _handle_clarifying(db, user, conv, text, user_priority, client_env)
    return await _handle_intake(db, user, conv, text, user_priority, client_env)


async def _handle_intake(db, user: User, conv: Conversation, text: str, user_priority, client_env) -> ChatReply:
    if GREETING.match(text):
        first = user.full_name.split()[0]
        return await _reply(db, conv, f"Hi {first}! Describe the IT issue you're facing - for example "
                                      f"\"My VPN times out after I enter my 2FA code\" - and I'll take it from there.")
    slots = _slots(conv)
    description = (slots.get("description", "") + "\n" + text).strip()
    slots["description"] = description
    if user_priority:
        slots["user_priority"] = user_priority
    if client_env:
        slots["client_env"] = client_env

    classification = await cls_svc.classify(description, db)
    if classification.method == "default" and len(description.split()) < 5:
        conv.slots = slots
        return await _reply(db, conv, DEFAULT_SYMPTOM[0])

    slots["category"] = classification.category
    slots["pending"] = _plan_questions(description, classification)
    conv.slots = slots
    return await _ask_next_or_create(db, user, conv)


def _plan_questions(description: str, c: cls_svc.Classification) -> list[str]:
    questions = []
    words = len(description.split())
    if (c.intent in GENERIC_INTENTS and words < 25) or c.method == "default":
        questions.append("symptom")
    scope_level, _ = detect_scope(description.lower(), c.entities)
    if scope_level == 0 and not re.search(r"\b(just me|only me|only my|only mine)\b", description.lower()):
        questions.append("scope")
    return questions


async def _ask_next_or_create(db, user: User, conv: Conversation) -> ChatReply:
    slots = _slots(conv)
    pending = slots.get("pending", [])
    if pending:
        q = pending[0]
        slots["asking"] = q
        conv.slots = slots
        conv.stage = "clarifying"
        if q == "symptom":
            text, options = SYMPTOM_QUESTIONS.get(slots.get("category") or "", DEFAULT_SYMPTOM)
        else:
            text, options = SCOPE_QUESTION
        progress = [{"key": "understand", "label": "Understanding issue", "status": "running"},
                    {"key": "classify", "label": "Classifying category", "status": "done" if slots.get("category") else "running"}]
        return await _reply(db, conv, text, quick_replies=options,
                            payload={"progress": progress, "draft": {"category": slots.get("category")}})
    return await _create_ticket_and_run_agent(db, user, conv)


async def _handle_clarifying(db, user: User, conv: Conversation, text: str, user_priority, client_env) -> ChatReply:
    slots = _slots(conv)
    asking = slots.get("asking")
    label = "Symptoms" if asking == "symptom" else "Scope"
    slots["description"] = f"{slots.get('description', '')}\n{label}: {text}".strip()
    slots.setdefault("answers", {})[asking or "extra"] = text
    slots["pending"] = [q for q in slots.get("pending", []) if q != asking]
    if user_priority:
        slots["user_priority"] = user_priority
    if client_env:
        slots["client_env"] = client_env
    conv.slots = slots
    return await _ask_next_or_create(db, user, conv)


async def _create_ticket_and_run_agent(db, user: User, conv: Conversation) -> ChatReply:
    slots = _slots(conv)
    description = slots["description"]
    c = await cls_svc.classify(description, db)
    p = await prio_svc.assess_priority(description, db, category=c.category, entities=c.entities,
                                       user_priority=slots.get("user_priority"))
    draft = TicketDraft(
        title=c.title or description[:80], description=description, category=c.category or "Software",
        category_id=c.category_id or 0, sub_category=c.sub_category, intent=c.intent,
        entities={k: str(v) for k, v in c.entities.items()}, ai_confidence=round(c.confidence, 3),
        classification_method=c.method, user_priority=p.user_priority, system_priority=p.system_priority,
        priority_confidence=p.confidence, priority_reason=p.reason, priority_impact=p.impact,
        priority_urgency=p.urgency,
    )
    ticket = await ticket_svc.create_ticket(
        db, user=user, title=draft.title, description=draft.description, category_id=draft.category_id,
        sub_category=draft.sub_category, intent=draft.intent, entities=draft.entities,
        ai_confidence=draft.ai_confidence, classification_method=draft.classification_method,
        user_priority=draft.user_priority, system_priority=draft.system_priority,
        priority_confidence=draft.priority_confidence, priority_reason=draft.priority_reason,
        priority_impact=draft.priority_impact, priority_urgency=draft.priority_urgency,
        extra_data={"client_env": slots.get("client_env", {}), "intake_answers": slots.get("answers", {})},
    )
    # Attach the conversation so far to the ticket
    for m in await history(db, conv):
        m.ticket_id = ticket.id
    conv.ticket_id = ticket.id
    conv.stage = "agent"
    await db.flush()
    await db.refresh(conv)
    await get_index_manager().index_ticket(ticket)

    alerts = []
    if p.alert:
        alerts.append({"type": "warning", "message": p.alert})
    outcome = await agent.start(db, ticket, user, client_env=slots.get("client_env"), intake={
        "classification": c.as_dict(), "priority": p.as_dict(), "alerts": alerts})
    if outcome.conversation_done:
        await close_conversation(db, conv)
    payload = {**outcome.payload, "priority_assessment": p.as_dict(), "classification": c.as_dict()}
    header = (f"I've created ticket **{ticket.ticket_number}** - {ticket.category_name} / "
              f"{ticket.sub_category or 'General'}, priority **{ticket.priority.upper()}**. ")
    return await _reply(db, conv, header + outcome.message, payload=payload, quick_replies=outcome.quick_replies)


async def _handle_agent_stage(db, user: User, conv: Conversation, text: str, user_priority, client_env) -> ChatReply:
    ticket = conv.ticket
    assert ticket is not None
    if YES.match(text) or NO.match(text):
        resolved = bool(YES.match(text)) and not NO.match(text)
        outcome = await agent.handle_feedback(db, ticket, user, resolved, comment=None if len(text) < 30 else text)
        if outcome.conversation_done:
            await close_conversation(db, conv)
        return await _reply(db, conv, outcome.message, payload=outcome.payload, quick_replies=outcome.quick_replies)

    # Something else: a brand-new issue, or extra detail about this one
    c = await cls_svc.classify(text, db, allow_llm=False)
    if c.category and c.category != ticket.category_name and c.confidence >= 0.6 and len(text.split()) >= 4:
        await close_conversation(db, conv)
        new_conv = await get_active_conversation(db, user)
        assert new_conv is not None
        await ticket_svc.add_message(db, role="user", content=text, conversation_id=new_conv.id, user_id=user.id)
        return await _handle_intake(db, user, new_conv, text, user_priority, client_env)
    await ticket_svc.add_event(db, ticket, "user_note", user_id=user.id, description=text[:500])
    return await _reply(db, conv, "Thanks, I've added that to the ticket. Did the steps above resolve the issue?",
                        quick_replies=["Yes, it's fixed", "No, still not working"])


async def new_conversation(db: AsyncSession, user: User) -> Conversation:
    conv = await get_active_conversation(db, user, create=False)
    if conv is not None:
        if conv.stage == "agent" and conv.ticket_id:
            run = await agent.active_run(db, conv.ticket_id)
            if run is not None and run.state == AgentState.VERIFY.value:
                # leaving an unanswered fix: keep the ticket open for follow-up from the ticket page
                await ticket_svc.add_event(db, conv.ticket, "chat_left", user_id=user.id,
                                           description="Employee started a new chat before confirming the fix")
        await close_conversation(db, conv)
    new = await get_active_conversation(db, user)
    assert new is not None
    return new
