"""Synchronous agent-chat endpoint for external clients such as OpenClaw."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.agent_runtime.service import AssistantService
from server.agent_runtime.session_manager import SessionCapacityError
from server.auth import CurrentUser
from server.routers.assistant import get_assistant_service

logger = logging.getLogger(__name__)

router = APIRouter()

SYNC_CHAT_TIMEOUT = 120  # seconds


class AgentChatRequest(BaseModel):
    project_name: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    message: str = Field(min_length=1)
    session_id: str | None = None


class AgentChatResponse(BaseModel):
    session_id: str
    reply: str
    status: str  # "completed" | "timeout" | "error"


def _extract_text_from_assistant_message(msg: dict) -> str:
    """Extract plain text from an assistant message payload."""
    content = msg.get("content", [])
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if text and isinstance(text, str):
            parts.append(text)
    return "".join(parts)


TERMINAL_RUNTIME_STATUSES = {"idle", "completed", "error", "interrupted"}


async def _collect_reply(
    service: AssistantService,
    session_id: str,
    timeout: float,
) -> tuple[str, str]:
    """Subscribe to the session queue and collect replies until completion or timeout."""
    queue = await service.session_manager.subscribe(session_id, replay_buffer=True)
    try:
        reply_parts: list[str] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                status = "timeout"
                break

            try:
                message = await asyncio.wait_for(queue.get(), timeout=min(remaining, 5.0))
            except TimeoutError:
                # Check whether the session has already finished.
                live_status = await service.session_manager.get_status(session_id)
                if live_status and live_status != "running":
                    status = "completed" if live_status in {"idle", "completed"} else live_status
                    break
                # Check for timeout.
                if loop.time() >= deadline:
                    status = "timeout"
                    break
                continue

            msg_type = message.get("type", "")

            if msg_type == "assistant":
                text = _extract_text_from_assistant_message(message)
                if text:
                    reply_parts.append(text)

            elif msg_type == "result":
                # Terminal message: stop collecting and finalize status.
                subtype = str(message.get("subtype") or "").lower()
                is_error = bool(message.get("is_error"))
                if is_error or subtype.startswith("error"):
                    status = "error"
                else:
                    status = "completed"
                break

            elif msg_type == "runtime_status":
                runtime_status = str(message.get("status") or "").strip()
                if runtime_status in TERMINAL_RUNTIME_STATUSES and runtime_status != "running":
                    status = "completed" if runtime_status in {"idle", "completed"} else runtime_status
                    break

            elif msg_type == "_queue_overflow":
                # Queue overflow: abort collection.
                status = "error"
                break

        return "".join(reply_parts), status

    finally:
        await service.session_manager.unsubscribe(session_id, queue)


@router.post("/agent/chat")
async def agent_chat(
    body: AgentChatRequest,
    _user: CurrentUser,
) -> AgentChatResponse:
    """Handle synchronous agent chat requests.

    If ``session_id`` is omitted, a new session is created. If it is provided,
    the conversation continues inside that existing session.
    """
    service = get_assistant_service()

    # Validate project existence first.
    try:
        service.pm.get_project_path(body.project_name)
    except (FileNotFoundError, KeyError):
        raise HTTPException(status_code=404, detail=f"Project '{body.project_name}' does not exist")

    # If a session id is supplied, verify ownership before sending the message.
    if body.session_id:
        session = await service.get_session(body.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session '{body.session_id}' does not exist")
        if session.project_name != body.project_name:
            raise HTTPException(
                status_code=400,
                detail=f"Session '{body.session_id}' belongs to project '{session.project_name}', not '{body.project_name}'",
            )

    # Use send_or_create for both new and existing sessions.
    # replay_buffer=True ensures there is no race with already-emitted events.
    try:
        result = await service.send_or_create(
            body.project_name,
            body.message,
            session_id=body.session_id,
        )
        session_id = result["session_id"]
    except SessionCapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="SDK session creation timed out")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # Collect the reply with timeout protection.
    reply, status = await _collect_reply(service, session_id, SYNC_CHAT_TIMEOUT)

    # If no text arrived through the queue, fall back to the latest assistant turn in the snapshot.
    if not reply:
        try:
            snapshot = await service.get_snapshot(session_id)
            turns = snapshot.get("turns", [])
            for turn in reversed(turns):
                if turn.get("role") == "assistant":
                    blocks = turn.get("content", [])
                    text_parts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
                    reply = "".join(text_parts)
                    if reply:
                        break
        except Exception as exc:
            logger.warning("Failed to fetch snapshot session_id=%s: %s", session_id, exc)

    return AgentChatResponse(
        session_id=session_id,
        reply=reply,
        status=status,
    )
