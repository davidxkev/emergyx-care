from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.db import get_session
from app.schemas import ChatMessageCreateRequest, ChatThreadCreateRequest
from app.services.chat_threads import (
    add_message,
    create_thread,
    delete_thread,
    get_thread,
    get_thread_detail,
    list_thread_messages,
    list_threads,
)
from app.services.gemma_agent import (
    answer_caregiver_question,
    stream_answer_caregiver_question,
)
from app.services.utils import json_safe_value
from app.services.utils import parse_mode


router = APIRouter(prefix="/chat", tags=["chat"])


def _stream_json(payload: object) -> str:
    return json.dumps(
        json_safe_value(payload),
        default=str,
        allow_nan=False,
    ) + "\n"


@router.get("/threads")
def get_threads(
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    normalized_mode, _ = parse_mode(mode)
    return {"threads": list_threads(session, mode=normalized_mode)}


@router.post("/threads")
def post_thread(
    payload: ChatThreadCreateRequest | None = None,
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    normalized_mode, _ = parse_mode(mode)
    request = payload or ChatThreadCreateRequest()
    thread = create_thread(session, mode=normalized_mode, title=request.title)
    return {"thread": thread}


@router.get("/threads/{thread_id}")
def get_thread_by_id(
    thread_id: int,
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    normalized_mode, _ = parse_mode(mode)
    detail = get_thread_detail(session, thread_id=thread_id, mode=normalized_mode)
    if detail is None:
        raise HTTPException(status_code=404, detail="Chat thread not found for this mode.")
    return detail


@router.delete("/threads/{thread_id}")
def delete_thread_by_id(
    thread_id: int,
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    normalized_mode, _ = parse_mode(mode)
    removed = delete_thread(session, thread_id=thread_id, mode=normalized_mode)
    if not removed:
        raise HTTPException(status_code=404, detail="Chat thread not found for this mode.")
    return {"success": True, "thread_id": thread_id}


@router.post("/threads/{thread_id}/messages")
def post_thread_message(
    thread_id: int,
    payload: ChatMessageCreateRequest,
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required.")

    normalized_mode, source_filter = parse_mode(mode)
    thread = get_thread(session, thread_id=thread_id, mode=normalized_mode)
    if thread is None:
        raise HTTPException(status_code=404, detail="Chat thread not found for this mode.")

    prior_messages = list_thread_messages(session, thread_id=thread_id)
    add_message(session, thread=thread, role="user", content=content)

    result = answer_caregiver_question(
        session,
        question=content,
        source_filter=source_filter,
        conversation_history=[
            {"role": item["role"], "content": item["content"]}
            for item in prior_messages[-6:]
        ],
        think=payload.think,
    )

    add_message(
        session,
        thread=thread,
        role="assistant",
        content=result.get("text", ""),
        model_name=result.get("model_name"),
        used_mock=result.get("used_mock"),
        metadata={
            "tools_used": result.get("tools_used", []),
            "evidence": result.get("evidence", []),
            "snapshot": result.get("snapshot"),
            "thinking": result.get("thinking"),
        },
    )

    detail = get_thread_detail(session, thread_id=thread_id, mode=normalized_mode)
    if detail is None:
        raise HTTPException(status_code=404, detail="Chat thread not found after update.")
    return detail


@router.post("/threads/{thread_id}/messages/stream")
def post_thread_message_stream(
    thread_id: int,
    payload: ChatMessageCreateRequest,
    mode: str = Query("demo", description="demo or live"),
    session: Session = Depends(get_session),
):
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required.")

    normalized_mode, source_filter = parse_mode(mode)
    thread = get_thread(session, thread_id=thread_id, mode=normalized_mode)
    if thread is None:
        raise HTTPException(status_code=404, detail="Chat thread not found for this mode.")

    prior_messages = list_thread_messages(session, thread_id=thread_id)
    add_message(session, thread=thread, role="user", content=content)

    def event_stream():
        generator = stream_answer_caregiver_question(
            session,
            question=content,
            source_filter=source_filter,
            conversation_history=[
                {"role": item["role"], "content": item["content"]}
                for item in prior_messages[-6:]
            ],
            think=payload.think,
        )

        result: dict[str, object] | None = None

        while True:
            try:
                event = next(generator)
            except StopIteration as stop:
                result = stop.value
                break

            yield _stream_json(event)

        if result is None:
            return

        add_message(
            session,
            thread=thread,
            role="assistant",
            content=str(result.get("text", "")),
            model_name=str(result.get("model_name", "")),
            used_mock=bool(result.get("used_mock", False)),
            metadata={
                "tools_used": result.get("tools_used", []),
                "evidence": result.get("evidence", []),
                "snapshot": result.get("snapshot"),
                "thinking": result.get("thinking"),
            },
        )

        detail = get_thread_detail(session, thread_id=thread_id, mode=normalized_mode)
        if detail is None:
            yield _stream_json({"type": "error", "error": "Chat thread not found after streaming update."})
            return

        yield _stream_json({"type": "done", "detail": detail})

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
