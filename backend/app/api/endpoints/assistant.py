"""
灵感助手专用接口
支持工具调用的对话
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import AsyncGenerator
from loguru import logger
import json

from app.db.session import get_session
from app.services.agent_service import generate_assistant_chat_streaming
from app.schemas.ai import AssistantChatRequest

router = APIRouter(prefix="/assistant", tags=["assistant"])


async def stream_wrapper(generator):
    """将纯文本流包装为SSE格式"""
    async for item in generator:
        yield f"data: {json.dumps({'content': item}, ensure_ascii=False)}\n\n"


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
    # 加载系统提示词
    from app.services import prompt_service
    p = prompt_service.get_prompt_by_name(session, request.prompt_name)
    if not p or not p.template:
        raise HTTPException(status_code=400, detail=f"未找到提示词: {request.prompt_name}")
    
    system_prompt = str(p.template)
    
    # 创建工具和依赖
    from app.services.assistant_tools.pydantic_ai_tools import ASSISTANT_TOOLS, AssistantDeps
    
    deps = AssistantDeps(session=session, project_id=request.project_id)
    
    # 调用灵感助手专用流式生成
    async def stream_with_tools() -> AsyncGenerator[str, None]:
        async for chunk in generate_assistant_chat_streaming(
            session=session,
            request=request,
            system_prompt=system_prompt,
            tools=ASSISTANT_TOOLS,  # 直接传函数列表
            deps=deps,
            track_stats=True
        ):
            yield chunk
    
    return StreamingResponse(
        stream_wrapper(stream_with_tools()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
