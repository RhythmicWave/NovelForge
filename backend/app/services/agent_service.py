from typing import Awaitable, Callable, Optional, Type, Any, Dict, AsyncGenerator, Union
from pydantic import BaseModel
from sqlmodel import Session
from app.services import llm_config_service
from loguru import logger
from app.schemas.ai import ContinuationRequest, AssistantChatRequest
from app.services import prompt_service
from app.db.models import LLMConfig
import asyncio
import json
import re
import os
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

_TOKEN_REGEX = re.compile(
    r"""
    ([A-Za-z]+)               # 英文单词（连续字母算 1）
    |([0-9])                 # 1个数字算 1
    |([\u4E00-\u9FFF])       # 单个中文汉字算 1
    |(\S)                     # 其它非空白符号/标点算 1
    """,
    re.VERBOSE,
)

def _estimate_tokens(text: str) -> int:
    """按规则估算 token：
    - 1 个中文 = 1
    - 1 个英文单词 = 1
    - 1 个数字 = 1
    - 1 个符号 = 1
    空白不计。
    """
    if not text:
        return 0
    try:
        return sum(1 for _ in _TOKEN_REGEX.finditer(text))
    except Exception:
        # 退化：按非空白字符计数
        return sum(1 for ch in (text or "") if not ch.isspace())

from app.services import llm_config_service as _llm_svc

def _calc_input_tokens(system_prompt: Optional[str], user_prompt: Optional[str]) -> int:
    sys_part = system_prompt or ""
    usr_part = user_prompt or ""
    return _estimate_tokens(sys_part+usr_part) 


def _precheck_quota(session: Session, llm_config_id: int, input_tokens: int, need_calls: int = 1) -> None:
    ok, reason = _llm_svc.can_consume(session, llm_config_id, input_tokens, 0, need_calls)
    return ok,reason


def _record_usage(session: Session, llm_config_id: int, input_tokens: int, output_tokens: int, calls: int = 1, aborted: bool = False) -> None:
    try:
        _llm_svc.accumulate_usage(session, llm_config_id, max(0, input_tokens), max(0, output_tokens), max(0, calls), aborted=aborted)
    except Exception as stat_e:
        logger.warning(f"记录 LLM 统计失败: {stat_e}")

def _build_continuation_chat_model(
    session: Session,
    llm_config_id: int,
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
):
    """兼容旧接口的占位函数，已统一改用 LangChain 助手的 build_chat_model。

    为避免循环依赖，实际构造逻辑委托给 app.services.langchain_assistant.build_chat_model。
    """

    from app.services.langchain_assistant import build_chat_model

    return build_chat_model(
        session=session,
        llm_config_id=llm_config_id,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )

async def run_llm_agent(
    session: Session,
    llm_config_id: int,
    user_prompt: str,
    output_type: Type[BaseModel],
    system_prompt: Optional[str] = None,
    deps: str = "",
    max_tokens: Optional[int] = None,
    max_retries: int = 3,
    temperature: Optional[float] = None,
    timeout: Optional[float] = None,
    track_stats: bool = True,) -> BaseModel:
    """运行结构化输出的 LLM 调用

    使用 LangChain ChatModel 的 structured output 能力：
      - 由 app.services.langchain_assistant.build_chat_model 构造底层模型
      - 通过 model.with_structured_output(output_type) 获取结构化输出
      - 仍然保留原有的配额预检、重试和统计逻辑
    """

    from app.services.langchain_assistant import build_chat_model

    # 限额预检（按估算的输入 tokens + 1 次调用）
    if track_stats:
        ok, reason = _precheck_quota(
            session,
            llm_config_id,
            _calc_input_tokens(system_prompt, user_prompt),
            need_calls=1,
        )
        if not ok:
            raise ValueError(f"LLM 配额不足:{reason}")

    logger.info(f"[LangChain-Structured] system_prompt: {system_prompt}")
    logger.info(f"[LangChain-Structured] user_prompt: {user_prompt}")

    last_exception = None
    for attempt in range(max_retries):
        try:
            # 构造底层 ChatModel
            model = build_chat_model(
                session=session,
                llm_config_id=llm_config_id,
                temperature=temperature or 0.7,
                max_tokens=max_tokens,
                timeout=timeout or 150,
            )

            # 结构化输出模型
            structured_llm = model.with_structured_output(output_type)

            messages = []
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            messages.append(HumanMessage(content=user_prompt))

            response = await structured_llm.ainvoke(messages)

            if response is None:
                raise ValueError("LLM 返回了空响应")

            logger.info(f"[LangChain-Structured] response: {response}")

            if track_stats:
                in_tokens = _calc_input_tokens(system_prompt, user_prompt)
                try:
                    out_text = (
                        response
                        if isinstance(response, str)
                        else json.dumps(response, ensure_ascii=False)
                    )
                except Exception:
                    out_text = str(response)
                out_tokens = _estimate_tokens(out_text)
                _record_usage(
                    session,
                    llm_config_id,
                    in_tokens,
                    out_tokens,
                    calls=1,
                    aborted=False,
                )

            return response

        except asyncio.CancelledError:
            logger.info("[LangChain-Structured] LLM 调用被取消（CancelledError），立即中止，不再重试。")
            if track_stats:
                in_tokens = _calc_input_tokens(system_prompt, user_prompt)
                _record_usage(
                    session,
                    llm_config_id,
                    in_tokens,
                    0,
                    calls=1,
                    aborted=True,
                )
            raise
        except Exception as e:
            last_exception = e
            logger.warning(
                f"[LangChain-Structured] 调用失败，重试 {attempt + 1}/{max_retries}，llm_config_id={llm_config_id}: {e}"
            )

    logger.error(
        f"[LangChain-Structured] 调用在重试 {max_retries} 次后仍失败，llm_config_id={llm_config_id}. Last error: {last_exception}"
    )
    raise ValueError(
        f"调用LLM服务失败，已重试 {max_retries} 次: {str(last_exception)}"
    )

async def generate_assistant_chat_streaming(
    session: Session,
    request: AssistantChatRequest,
    system_prompt: str,
    track_stats: bool = True) -> AsyncGenerator[str, None]:
    """灵感助手专用流式对话生成（结构化事件流协议，LangChain-only）。

    当前实现完全基于 LangChain ChatModel + LangChain Tools，实现工具调用与事件流：
      - token
      - tool_start
      - tool_end
    不再复用 pydantic_ai 的 Agent/图结构。
    """

    from app.services.langchain_assistant import (
        stream_chat_with_tools,
        stream_chat_with_react,
    )

    react_enabled = bool(getattr(request, "react_mode_enabled", False))
    logger.info("[LangChain] generate_assistant_chat_streaming: 使用{}模式".format("React" if react_enabled else "标准"))

    engine = stream_chat_with_react if react_enabled else stream_chat_with_tools

    try:
        async for evt in engine(
            session=session,
            request=request,
            system_prompt=system_prompt,
        ):
            # LangChain 分支直接产出事件 dict，这里统一转成 JSON-line 协议
            yield json.dumps(evt, ensure_ascii=False)
    except asyncio.CancelledError:
        logger.info("[LangChain] 助手调用被取消（CancelledError）")
        # 具体的 token 统计已在 LangChain 助手内部完成
        return
    except Exception as e:
        logger.error(f"[LangChain] 灵感助手生成失败: {e}")
        error_event = {
            "type": "error",
            "data": {"error": str(e)},
        }
        yield json.dumps(error_event, ensure_ascii=False)
        raise


async def generate_continuation_streaming(session: Session, request: ContinuationRequest, system_prompt: str, track_stats: bool = True) -> AsyncGenerator[str, None]:
    """以流式方式生成续写内容。system_prompt 由外部显式传入。"""
    # 组装用户消息
    user_prompt_parts = []
    
    # 1. 添加上下文信息（引用上下文 + 事实子图）
    context_info = (getattr(request, 'context_info', None) or '').strip()
    if context_info:
        # 检测 context_info 是否已包含结构化标记（如【引用上下文】、【上文】等）
        has_structured_marks = any(mark in context_info for mark in ['【引用上下文】', '【上文】', '【需要润色', '【需要扩写'])
        
        if has_structured_marks:
            # 已经是结构化的上下文，直接使用，不再额外包裹
            user_prompt_parts.append(context_info)
        else:
            # 未结构化的上下文（老格式），添加标记
            user_prompt_parts.append(f"【参考上下文】\n{context_info}")
    
    # 2. 添加已有章节内容（仅当 previous_content 非空时）
    previous_content = (request.previous_content or '').strip()
    if previous_content:
        user_prompt_parts.append(f"【已有章节内容】\n{previous_content}")
        
        # 添加字数统计信息
        existing_word_count = getattr(request, 'existing_word_count', None)
        if existing_word_count is not None:
            user_prompt_parts.append(f"（已有内容字数：{existing_word_count} 字）")
        
        # 续写指令
        if getattr(request, 'append_continuous_novel_directive', True):
            user_prompt_parts.append("【指令】请接着上述内容继续写作，保持文风和剧情连贯。直接输出小说正文。")
    else:
        # 新写模式或润色/扩写模式（previous_content 为空）
        # 只在需要时添加指令
        if getattr(request, 'append_continuous_novel_directive', True):
            # 如果 context_info 中有续写相关标记，说明是续写场景
            if context_info and '【已有章节内容】' in context_info:
                user_prompt_parts.append("【指令】请接着上述内容继续写作，保持文风和剧情连贯。直接输出小说正文。")
            else:
                user_prompt_parts.append("【指令】请开始创作新章节。直接输出小说正文。")
    
    user_prompt = "\n\n".join(user_prompt_parts)
    
    # 限额预检
    if track_stats:
        ok, reason = _precheck_quota(session, request.llm_config_id, _calc_input_tokens(system_prompt, user_prompt), need_calls=1)
        if not ok:
            raise ValueError(f"LLM 配额不足:{reason}")

    # 使用 LangChain ChatModel 进行流式续写
    model = _build_continuation_chat_model(
        session=session,
        llm_config_id=request.llm_config_id,
        temperature=request.temperature or 0.7,
        max_tokens=request.max_tokens,
        timeout=request.timeout or 64,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    accumulated: str = ""

    try:
        logger.debug("正在以 LangChain ChatModel 流式生成续写内容")
        async for chunk in model.astream(messages):
            content = getattr(chunk, "content", None)
            if not content:
                continue

            if isinstance(content, str):
                delta = content
            elif isinstance(content, list):
                texts = [
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                ]
                delta = "".join(texts)
            else:
                delta = str(content)

            if not delta:
                continue

            accumulated += delta
            yield delta

    except asyncio.CancelledError:
        logger.info("流式 LLM 调用被取消（CancelledError），停止推送。")
        if track_stats:
            in_tokens = _calc_input_tokens(system_prompt, user_prompt)
            out_tokens = _estimate_tokens(accumulated)
            _record_usage(session, request.llm_config_id, in_tokens, out_tokens, calls=1, aborted=True)
        return
    except Exception as e:
        logger.error(f"流式 LLM 调用失败: {e}")
        raise

    # 正常结束后统计
    try:
        if track_stats:
            in_tokens = _calc_input_tokens(system_prompt, user_prompt)
            out_tokens = _estimate_tokens(accumulated)
            _record_usage(session, request.llm_config_id, in_tokens, out_tokens, calls=1, aborted=False)
    except Exception as stat_e:
        logger.warning(f"记录 LLM 流式统计失败: {stat_e}")