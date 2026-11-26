from typing import Annotated
from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.security import HTTPBasicCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.chat import confirm_action, owned_session, respond, save_message
from app.database import get_db
from app.models import ChatMessage, ChatSession, PendingAction, User
from app.rag import MAX_UPLOAD, index_document
from app.schemas import ChatInput, ConfirmInput
from app.security import admin_user, basic, current_user

router = APIRouter(prefix="/api")
Db = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]
Admin = Annotated[User, Depends(admin_user)]
Credentials = Annotated[HTTPBasicCredentials, Depends(basic)]

@router.post("/documents", status_code=201)
async def upload_document(db: Db, admin: Admin, file: UploadFile = File(...)):
    data = await file.read(MAX_UPLOAD + 1)
    return index_document(db, admin.id, file.filename or "", data)

@router.post("/chat/sessions", status_code=201)
def create_session(db: Db, user: CurrentUser):
    session = ChatSession(user_id=user.id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"id": session.id, "title": session.title}

@router.get("/chat/sessions")
def sessions(db: Db, user: CurrentUser):
    rows = db.scalars(select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.id.desc())).all()
    return [{"id": row.id, "title": row.title} for row in rows]

@router.get("/chat/sessions/{session_id}/messages")
def messages(session_id: int, db: Db, user: CurrentUser, after: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=100)):
    owned_session(db, user.id, session_id)
    rows = db.scalars(select(ChatMessage).where(ChatMessage.session_id == session_id, ChatMessage.seq_no > after).order_by(ChatMessage.seq_no).limit(limit)).all()
    pending = db.scalars(select(PendingAction).where(PendingAction.session_id == session_id, PendingAction.user_id == user.id)).all()
    statuses = {row.id: row.status for row in pending}
    result = []
    for row in rows:
        details = dict(row.details)
        details["pending_actions"] = [{**action, "status": statuses.get(action["pending_action_id"], "EXPIRED")} for action in details.get("pending_actions", [])]
        result.append({"id": row.id, "seq_no": row.seq_no, "role": row.role, "content": row.content, **details})
    return result

@router.post("/chat/sessions/{session_id}/messages")
def message(session_id: int, body: ChatInput, db: Db, user: CurrentUser, credentials: Credentials):
    session = owned_session(db, user.id, session_id)
    return respond(db, session, user, (credentials.username, credentials.password), body.message)

@router.post("/chat/actions/{action_id}/confirm")
def confirm(action_id: int, body: ConfirmInput, db: Db, user: CurrentUser, credentials: Credentials):
    action = db.scalar(select(PendingAction).where(PendingAction.id == action_id, PendingAction.user_id == user.id))
    already_done = action and action.status in {"CONFIRMED", "REJECTED"}
    result = confirm_action(db, user, (credentials.username, credentials.password), action_id, body.confirm)
    if not already_done and action:
        session = owned_session(db, user.id, action.session_id)
        text = f"Action rejected." if not body.confirm else f"Action completed. Order #{result['id']} is {result['status'].lower()}."
        save_message(db, session, "assistant", text, {"mode": "AGENT", "citations": [], "pending_actions": []})
    return result