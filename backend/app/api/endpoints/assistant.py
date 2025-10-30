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
from app.services.agent_service import generate_assistant_chat_streaming, generate_assistant_chat_streaming_react
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
    # 加载系统提示词（根据模式选择不同的提示词）
    from app.services import prompt_service
    
    prompt_name = request.prompt_name
    if request.use_react_mode and request.prompt_name == "灵感对话":
        # ReAct 模式使用专用提示词
        prompt_name = "灵感对话-React"
    
    p = prompt_service.get_prompt_by_name(session, prompt_name)
    if not p or not p.template:
        raise HTTPException(status_code=400, detail=f"未找到提示词: {prompt_name}")
    
    system_prompt = str(p.template)
    
    # 根据模式选择生成函数
    async def stream_with_tools() -> AsyncGenerator[str, None]:
        if request.use_react_mode:
            # ReAct 模式：文本格式工具调用
            logger.info(f"[Assistant API] 使用 ReAct 模式")
            async for chunk in generate_assistant_chat_streaming_react(
                session=session,
                request=request,
                system_prompt=system_prompt,
                track_stats=True
            ):
                yield chunk
        else:
            # 标准模式：原生 Function Calling
            logger.info(f"[Assistant API] 使用标准模式（Function Calling）")
            from app.services.assistant_tools.pydantic_ai_tools import ASSISTANT_TOOLS, AssistantDeps
            
            deps = AssistantDeps(session=session, project_id=request.project_id)
            
            async for chunk in generate_assistant_chat_streaming(
                session=session,
                request=request,
                system_prompt=system_prompt,
                tools=ASSISTANT_TOOLS,
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
