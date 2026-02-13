"""灵感助手服务

提供基于 LangChain 的工具调用与流式对话能力。
React 文本协议模式与 Workflow Agent 共享核心实现。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

from loguru import logger
from sqlmodel import Session

from app.schemas.ai import AssistantChatRequest
from app.services.ai.core.react_text_agent import stream_chat_with_react_protocol
from app.services.ai.core.tool_agent_stream import stream_agent_with_tools
from .tools import (
    ASSISTANT_TOOL_DESCRIPTIONS,
    ASSISTANT_TOOL_REGISTRY,
    ASSISTANT_TOOLS,
    AssistantDeps,
    set_assistant_deps,
)


MAX_REACT_STEPS = 100


async def stream_chat_with_react(
    session: Session,
    request: AssistantChatRequest,
    system_prompt: str,
) -> AsyncGenerator[dict, None]:
    deps = AssistantDeps(session=session, project_id=request.project_id)
    async for event in stream_chat_with_react_protocol(
        session=session,
        llm_config_id=request.llm_config_id,
        system_prompt=system_prompt,
        context_info=request.context_info or "",
        user_prompt=request.user_prompt or "",
        tool_registry=ASSISTANT_TOOL_REGISTRY,
        tool_descriptions=ASSISTANT_TOOL_DESCRIPTIONS,
        set_deps=set_assistant_deps,
        deps=deps,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        timeout=request.timeout,
        thinking_enabled=getattr(request, "thinking_enabled", None),
        max_steps=MAX_REACT_STEPS,
        log_tag="Assistant-React",
    ):
        yield event


async def stream_chat_with_tools(
    session: Session,
    request: AssistantChatRequest,
    system_prompt: str,
) -> AsyncGenerator[dict, None]:
    """标准模式：复用共享 Tool Agent 流式核心。"""
    parts: list[str] = []
    if request.context_info:
        parts.append(request.context_info)
    if request.user_prompt:
        parts.append("\nUser: " + request.user_prompt)
    final_user_prompt = "\n\n".join(parts) if parts else "(User input is empty; assistant should clarify intent first.)"

    enable_summarization = getattr(request, "context_summarization_enabled", None)
    max_tokens_before_summary = (
        int(request.context_summarization_threshold)
        if getattr(request, "context_summarization_threshold", None)
        else 8192
    )

    deps = AssistantDeps(session=session, project_id=request.project_id)

    async for event in stream_agent_with_tools(
        session=session,
        llm_config_id=request.llm_config_id,
        system_prompt=system_prompt,
        user_prompt=final_user_prompt,
        tools=ASSISTANT_TOOLS,
        set_deps=set_assistant_deps,
        deps=deps,
        temperature=request.temperature or 0.6,
        max_tokens=request.max_tokens or 8192,
        timeout=request.timeout or 90,
        thinking_enabled=getattr(request, "thinking_enabled", None),
        enable_summarization=bool(enable_summarization),
        max_tokens_before_summary=max_tokens_before_summary,
        log_tag="LangChain+Agent",
    ):
        yield event


async def generate_assistant_chat_streaming(
    session: Session,
    request: AssistantChatRequest,
    system_prompt: str,
    track_stats: bool = True,
) -> AsyncGenerator[str, None]:
    """灵感助手专用流式对话生成（结构化事件流协议）。"""
    _ = track_stats
    react_enabled = bool(getattr(request, "react_mode_enabled", False))
    logger.info(
        "[LangChain] generate_assistant_chat_streaming: 使用{}模式",
        "React" if react_enabled else "标准",
    )

    engine = stream_chat_with_react if react_enabled else stream_chat_with_tools

    try:
        async for evt in engine(
            session=session,
            request=request,
            system_prompt=system_prompt,
        ):
            yield json.dumps(evt, ensure_ascii=False)
    except asyncio.CancelledError:
        logger.info("[LangChain] 助手调用被取消（CancelledError）")
        return
    except Exception as exc:
        logger.error("[LangChain] 灵感助手生成失败: {}", exc)
        error_event = {
            "type": "error",
            "data": {"error": str(exc)},
        }
        yield json.dumps(error_event, ensure_ascii=False)
        raise

