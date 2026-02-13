from __future__ import annotations

from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.workflow_agent import WorkflowAgentChatRequest
from app.services.ai.workflow_agent.agent_service import (
    generate_workflow_agent_chat_streaming,
    get_workflow_agent_system_prompt,
)
from app.utils.stream_utils import wrap_sse_stream


router = APIRouter(prefix="/workflow-agent", tags=["workflow-agent"])


@router.post("/chat")
async def workflow_agent_chat(
    request: WorkflowAgentChatRequest,
    session: Session = Depends(get_session),
):
    react_enabled = bool(getattr(request, "react_mode_enabled", False))
    system_prompt = get_workflow_agent_system_prompt(session, react_enabled=react_enabled)

    async def stream_with_tools() -> AsyncGenerator[str, None]:
        async for chunk in generate_workflow_agent_chat_streaming(
            session=session,
            request=request,
            system_prompt=system_prompt,
        ):
            yield chunk

    return StreamingResponse(
        wrap_sse_stream(stream_with_tools()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
