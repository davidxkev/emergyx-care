from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from app.models import ChatMessage, ChatThread
from app.services.utils import current_timestamp, json_safe_value, normalize_metadata


def _thread_to_dict(thread: ChatThread) -> dict[str, Any]:
    return {
        "id": thread.id,
        "title": thread.title,
        "mode": thread.mode,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
        "metadata": json_safe_value(_load_json(thread.metadata_json)),
    }


def _message_to_dict(message: ChatMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "thread_id": message.thread_id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at,
        "model_name": message.model_name,
        "used_mock": message.used_mock,
        "metadata": json_safe_value(_load_json(message.metadata_json)),
    }


def _load_json(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def _default_thread_title(title: str | None = None) -> str:
    clean = (title or "").strip()
    return clean[:80] if clean else "New caregiver chat"


def _derive_thread_title_from_question(question: str) -> str:
    clean = " ".join(question.strip().split())
    if not clean:
        return "New caregiver chat"
    return clean[:60]


def list_threads(
    session: Session,
    *,
    mode: str,
    limit: int = 24,
) -> list[dict[str, Any]]:
    statement = (
        select(ChatThread)
        .where(ChatThread.mode == mode)
        .order_by(ChatThread.updated_at.desc(), ChatThread.id.desc())
        .limit(limit)
    )
    return [_thread_to_dict(thread) for thread in session.exec(statement)]


def create_thread(
    session: Session,
    *,
    mode: str,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = current_timestamp()
    thread = ChatThread(
        title=_default_thread_title(title),
        mode=mode,
        created_at=now,
        updated_at=now,
        metadata_json=normalize_metadata(metadata),
    )
    session.add(thread)
    session.commit()
    session.refresh(thread)
    return _thread_to_dict(thread)


def get_thread(
    session: Session,
    *,
    thread_id: int,
    mode: str,
) -> ChatThread | None:
    statement = (
        select(ChatThread)
        .where(ChatThread.id == thread_id)
        .where(ChatThread.mode == mode)
        .limit(1)
    )
    return session.exec(statement).first()


def list_thread_messages(
    session: Session,
    *,
    thread_id: int,
) -> list[dict[str, Any]]:
    statement = (
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.id.asc())
    )
    return [_message_to_dict(message) for message in session.exec(statement)]


def get_thread_detail(
    session: Session,
    *,
    thread_id: int,
    mode: str,
) -> dict[str, Any] | None:
    thread = get_thread(session, thread_id=thread_id, mode=mode)
    if thread is None:
        return None
    return {
        "thread": _thread_to_dict(thread),
        "messages": list_thread_messages(session, thread_id=thread.id or 0),
    }


def delete_thread(
    session: Session,
    *,
    thread_id: int,
    mode: str,
) -> bool:
    thread = get_thread(session, thread_id=thread_id, mode=mode)
    if thread is None:
        return False

    messages = session.exec(
        select(ChatMessage).where(ChatMessage.thread_id == thread_id)
    )
    for message in messages:
        session.delete(message)
    session.delete(thread)
    session.commit()
    return True


def add_message(
    session: Session,
    *,
    thread: ChatThread,
    role: str,
    content: str,
    model_name: str | None = None,
    used_mock: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = current_timestamp()
    message = ChatMessage(
        thread_id=thread.id or 0,
        role=role,
        content=content,
        created_at=now,
        model_name=model_name,
        used_mock=used_mock,
        metadata_json=normalize_metadata(metadata),
    )
    session.add(message)

    if role == "user" and thread.title == "New caregiver chat":
        thread.title = _derive_thread_title_from_question(content)
    thread.updated_at = now
    session.add(thread)

    session.commit()
    session.refresh(message)
    session.refresh(thread)
    return _message_to_dict(message)
