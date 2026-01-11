"""
灵感助手专用接口
支持工具调用的对话
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import AsyncGenerator
from loguru import logger

from app.db.session import get_session
from app.services.ai.assistant_service import generate_assistant_chat_streaming
from app.schemas.ai import AssistantChatRequest
from app.utils.stream_utils import wrap_sse_stream

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/chat")
async def assistant_chat(
    request: AssistantChatRequest,
    session: Session = Depends(get_session)
):
    """
    灵感助手对话接口（支持工具调用）
    
    特点：
    - 专用请求模型（语义清晰）
    - 自动注入工具集
    - 支持流式输出
    - 支持工具调用结果返回
    """
    # 加载系统提示词（根据模式选择不同的提示词）
    from app.services import prompt_service
    
    prompt_name = request.prompt_name
    react_enabled = bool(getattr(request, "react_mode_enabled", False))

    if react_enabled:
        react_prompt_name = f"{prompt_name}-React"
        p = prompt_service.get_prompt_by_name(session, react_prompt_name)
        if p and p.template:
            system_prompt = str(p.template)
            logger.info(f"[Assistant API] React 模式启用，使用提示词 {react_prompt_name}")
        else:
            logger.warning(f"[Assistant API] React 模式启用但未找到 {react_prompt_name}，退回标准提示词 {prompt_name}")
            p = prompt_service.get_prompt_by_name(session, prompt_name)
            if not p or not p.template:
                raise HTTPException(status_code=400, detail=f"未找到提示词: {prompt_name}")
            system_prompt = str(p.template)
    else:
        p = prompt_service.get_prompt_by_name(session, prompt_name)
        if not p or not p.template:
            raise HTTPException(status_code=400, detail=f"未找到提示词: {prompt_name}")
        system_prompt = str(p.template)
    
    # 所有模式统一走 LangChain ChatModel + Tools 管线
    async def stream_with_tools() -> AsyncGenerator[str, None]:
        logger.info("[Assistant API] 使用{}模式".format("React" if react_enabled else "标准"))
        async for chunk in generate_assistant_chat_streaming(
            session=session,
            request=request,
            system_prompt=system_prompt,
            track_stats=True,
        ):
            yield chunk
    
    return StreamingResponse(
        wrap_sse_stream(stream_with_tools()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
