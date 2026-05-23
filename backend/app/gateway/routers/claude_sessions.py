from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from deerflow.claude_session.models import SessionConfig, SessionStatus
from deerflow.tools.claude_session_tools import get_claude_session_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/claude-sessions", tags=["claude-sessions"])


class CreateSessionRequest(BaseModel):
    thread_id: str = Field(..., description="关联的线程 ID")
    working_directory: str | None = Field(default=None, description="工作目录")
    system_prompt_suffix: str = Field(default="", description="系统提示后缀")
    tool_permissions: list[str] = Field(default_factory=list, description="工具权限列表")
    timeout_seconds: int | None = Field(default=None, description="超时秒数")


class SendMessageRequest(BaseModel):
    message: str = Field(..., description="发送给 Claude Code 的消息")


class SessionResponse(BaseModel):
    session_id: str
    thread_id: str
    status: str
    working_directory: str | None
    message_count: int
    created_at: str
    last_active_at: str
    error: str | None = None


class MessageResponse(BaseModel):
    session_id: str
    role: str
    content: str
    timestamp: str


def _session_to_response(session) -> SessionResponse:
    return SessionResponse(
        session_id=session.session_id,
        thread_id=session.thread_id,
        status=session.status.value,
        working_directory=session.working_directory,
        message_count=session.message_count,
        created_at=session.created_at.isoformat(),
        last_active_at=session.last_active_at.isoformat(),
        error=session.error,
    )


@router.post("/", response_model=SessionResponse, status_code=201, summary="Create Session", description="创建 Claude Code 会话")
async def create_session(request: CreateSessionRequest) -> SessionResponse:
    manager = get_claude_session_manager()
    try:
        session = await manager.create_session(
            thread_id=request.thread_id,
            working_directory=request.working_directory,
            system_prompt_suffix=request.system_prompt_suffix,
            tool_permissions=request.tool_permissions,
            timeout_seconds=request.timeout_seconds,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return _session_to_response(session)


@router.get("/", response_model=list[SessionResponse], summary="List Sessions", description="列出指定线程的 Claude Code 会话")
async def list_sessions(thread_id: str) -> list[SessionResponse]:
    manager = get_claude_session_manager()
    sessions = await manager.list_sessions(thread_id)
    return [_session_to_response(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionResponse, summary="Get Session", description="获取 Claude Code 会话详情")
async def get_session(session_id: str) -> SessionResponse:
    manager = get_claude_session_manager()
    try:
        session = await manager.get_session(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _session_to_response(session)


@router.post("/{session_id}/send", response_model=SessionResponse, summary="Send Message", description="向 Claude Code 会话发送消息")
async def send_message(session_id: str, request: SendMessageRequest) -> SessionResponse:
    manager = get_claude_session_manager()
    try:
        await manager.send_message(session_id, request.message)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    session = await manager.get_session(session_id)
    return _session_to_response(session)


@router.post("/{session_id}/pause", response_model=SessionResponse, summary="Pause Session", description="暂停 Claude Code 会话")
async def pause_session(session_id: str) -> SessionResponse:
    manager = get_claude_session_manager()
    try:
        await manager.pause_session(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    session = await manager.get_session(session_id)
    return _session_to_response(session)


@router.post("/{session_id}/resume", response_model=SessionResponse, summary="Resume Session", description="恢复 Claude Code 会话")
async def resume_session(session_id: str) -> SessionResponse:
    manager = get_claude_session_manager()
    try:
        await manager.resume_session(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    session = await manager.get_session(session_id)
    return _session_to_response(session)


@router.delete("/{session_id}", response_model=SessionResponse, summary="Terminate Session", description="终止 Claude Code 会话")
async def terminate_session(session_id: str) -> SessionResponse:
    manager = get_claude_session_manager()
    try:
        session = await manager.get_session(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await manager.terminate_session(session_id)
    return _session_to_response(session)


@router.get("/{session_id}/stream", summary="Stream Session Output", description="SSE 流式输出 Claude Code 会话结果")
async def stream_session_output(session_id: str, request: Request) -> EventSourceResponse:
    manager = get_claude_session_manager()
    try:
        await manager.get_session(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    async def event_generator():
        try:
            async for chunk in manager.stream_output(session_id):
                if await request.is_disconnected():
                    break
                if chunk["type"] == "end":
                    yield {"event": "claude_end", "data": json.dumps({"session_id": session_id})}
                    break
                yield {"event": f"claude_{chunk['type']}", "data": json.dumps(chunk)}
        finally:
            pass

    return EventSourceResponse(event_generator())


@router.get("/{session_id}/messages", response_model=list[MessageResponse], summary="Get Messages", description="获取 Claude Code 会话消息历史")
async def get_messages(session_id: str) -> list[MessageResponse]:
    manager = get_claude_session_manager()
    try:
        messages = await manager.get_messages(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return [
        MessageResponse(
            session_id=m.session_id,
            role=m.role,
            content=m.content,
            timestamp=m.timestamp.isoformat(),
        )
        for m in messages
    ]
