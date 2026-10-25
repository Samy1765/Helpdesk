"""
Precision AI - Chatbot endpoints (primary employee experience) and attachments.
"""

import secrets
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import iso, message_out
from app.core.config import get_settings
from app.core.deps import get_current_user, is_staff
from app.core.ratelimit import enforce_chat_budget
from app.database import get_db
from app.models.attachment import Attachment
from app.models.ticket import Ticket
from app.models.user import User
from app.services import chat as chat_svc, tickets as ticket_svc, uploads

router = APIRouter(tags=["Chat"])
settings = get_settings()

# Browser-reported device facts the diagnostics may use; anything else is dropped
CLIENT_ENV_KEYS = ("platform", "user_agent", "language", "timezone", "online")


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_priority: Optional[Literal["low", "medium", "high", "critical"]] = None
    client_env: Optional[dict[str, str]] = None
    attachment_tokens: list[str] = Field(default_factory=list, max_length=5)


def _reply_out(r: chat_svc.ChatReply) -> dict:
    return {"conversation_id": r.conversation_id, "message": r.message, "stage": r.stage, "payload": r.payload,
            "quick_replies": r.quick_replies, "ticket_id": r.ticket_id, "ticket_number": r.ticket_number,
            "message_id": r.message_id}


@router.get("/chat/conversation")
async def get_conversation(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conv = await chat_svc.get_active_conversation(db, user)
    assert conv is not None
    msgs = await chat_svc.history(db, conv)
    return {"id": conv.id, "stage": conv.stage, "ticket_id": conv.ticket_id,
            "ticket_number": conv.ticket.ticket_number if conv.ticket else None,
            "created_at": iso(conv.created_at), "messages": [message_out(m) for m in msgs]}


@router.post("/chat/message")
async def send_message(data: ChatIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    enforce_chat_budget(user.id)
    client_env = {k: v[:300] for k, v in (data.client_env or {}).items() if k in CLIENT_ENV_KEYS}
    own = []
    if data.attachment_tokens:
        own = list((await db.execute(select(Attachment).where(Attachment.token.in_(data.attachment_tokens),
                                                              Attachment.user_id == user.id))).scalars().all())
    attachments = [{"token": a.token, "filename": a.filename, "content_type": a.content_type,
                    "size": a.size_bytes} for a in own]
    reply = await chat_svc.handle_message(db, user, data.message, user_priority=data.user_priority,
                                          client_env=client_env, attachments=attachments)
    if reply.ticket_id:
        for a in own:  # only the caller's own uploads are ever linked to the caller's ticket
            a.ticket_id = a.ticket_id or reply.ticket_id
    return _reply_out(reply)


@router.post("/chat/new")
async def new_chat(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conv = await chat_svc.new_conversation(db, user)
    return {"id": conv.id, "stage": conv.stage, "messages": []}


@router.post("/attachments", status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile = File(...), ticket_id: Optional[int] = Form(None),
                 db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Upload a screenshot/log. Linked to `ticket_id` when given (requester or IT staff only),
    otherwise to the caller's active chat conversation."""
    target_ticket = None
    if ticket_id is not None:
        target_ticket = await db.get(Ticket, ticket_id)
        if target_ticket is None or (target_ticket.user_id != user.id and not is_staff(user)):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    data = await file.read(settings.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Files can be at most {settings.MAX_UPLOAD_MB} MB")
    try:
        # type comes from the bytes and the extension, never from the client's Content-Type header
        filename, content_type = uploads.validate(file.filename, data)
    except uploads.UploadRejected as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc))
    token = secrets.token_urlsafe(24)
    folder = Path(settings.UPLOAD_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    path = uploads.storage_path(folder, token, content_type)  # random name: the client's name never touches disk
    path.write_bytes(data)
    conv = None if target_ticket else await chat_svc.get_active_conversation(db, user)
    att = Attachment(token=token, user_id=user.id, conversation_id=conv.id if conv else None,
                     ticket_id=target_ticket.id if target_ticket else (conv.ticket_id if conv else None),
                     filename=filename, content_type=content_type, size_bytes=len(data), storage_path=str(path))
    db.add(att)
    await db.flush()
    if target_ticket:
        await ticket_svc.add_event(db, target_ticket, "attachment_added", user_id=user.id, new_value=att.filename,
                                   description=f"Attachment added: {att.filename}")
    return {"token": token, "filename": att.filename, "content_type": att.content_type, "size": att.size_bytes}


@router.get("/attachments/{token}")
async def download(token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    att = (await db.execute(select(Attachment).where(Attachment.token == token))).scalar_one_or_none()
    allowed = att is not None and (att.user_id == user.id or is_staff(user))
    if att is not None and not allowed and att.ticket_id:
        ticket = await db.get(Ticket, att.ticket_id)  # the requester may read files IT added to their ticket
        allowed = ticket is not None and ticket.user_id == user.id
    path = uploads.inside(Path(settings.UPLOAD_DIR), att.storage_path) if allowed else None
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")
    # Content-Disposition: attachment, plus the global nosniff header: never rendered inline by the browser
    return FileResponse(path, media_type=att.content_type, filename=att.filename)
