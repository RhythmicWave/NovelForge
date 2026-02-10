"""通用LLM服务

提供ChatModel构建、结构化生成和续写功能。
"""

from typing import Any, Dict, Type, Optional, AsyncGenerator
from pydantic import BaseModel
from sqlmodel import Session
from loguru import logger
import asyncio
import json

from langchain_core.messages import HumanMessage, SystemMessage
from app.services.ai.generation.structured_runtime import (
    generate_structured_via_instruction_flow_model,
)
from app.schemas.ai import ContinuationRequest
from .chat_model_factory import build_chat_model
from .token_utils import calc_input_tokens, estimate_tokens
from .quota_manager import precheck_quota, record_usage


async def generate_structured(
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
    track_stats: bool = True,
    use_instruction_flow: bool = False,
    return_logs: bool = False,
) -> BaseModel | Dict[str, Any]:
    """结构化输出生成
    
    使用LangChain ChatModel的structured output能力。
    
    Args:
        session: 数据库会话
        llm_config_id: LLM配置ID
        user_prompt: 用户提示词
        output_type: 输出Pydantic模型类型
        system_prompt: 系统提示词
        deps: 依赖项（预留）
        max_tokens: 最大token数
        max_retries: 最大重试次数
        temperature: 温度参数
        timeout: 超时时间
        track_stats: 是否记录统计
        
    Returns:
        结构化输出对象
    """
    if use_instruction_flow:
        return await generate_structured_via_instruction_flow_model(
            session=session,
            llm_config_id=llm_config_id,
            user_prompt=user_prompt,
            output_type=output_type,
            system_prompt=system_prompt,
            deps=deps,
            max_tokens=max_tokens,
            max_retries=max_retries,
            temperature=temperature,
            timeout=timeout,
            track_stats=track_stats,
            return_logs=return_logs,
        )

    native_result = await _generate_structured_native(
        session=session,
        llm_config_id=llm_config_id,
        user_prompt=user_prompt,
        output_type=output_type,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        max_retries=max_retries,
        temperature=temperature,
        timeout=timeout,
        track_stats=track_stats,
    )

    if return_logs:
        return {
            "result": native_result,
            "logs": [],
        }

    return native_result


async def _generate_structured_native(
    *,
    session: Session,
    llm_config_id: int,
    user_prompt: str,
    output_type: Type[BaseModel],
    system_prompt: Optional[str],
    max_tokens: Optional[int],
    max_retries: int,
    temperature: Optional[float],
    timeout: Optional[float],
    track_stats: bool,
) -> BaseModel:
    """原生结构化输出实现（LangChain with_structured_output）。"""

    # 配额预检
    if track_stats:
        ok, reason = precheck_quota(
            session, llm_config_id,
            calc_input_tokens(system_prompt, user_prompt),
            need_calls=1
        )
        if not ok:
            raise ValueError(f"LLM配额不足: {reason}")

    last_exception = None
    for attempt in range(max_retries):
        try:
            model = build_chat_model(
                session=session,
                llm_config_id=llm_config_id,
                temperature=temperature or 0.7,
                max_tokens=max_tokens or 4096,
                timeout=timeout or 150,
            )

            structured_llm = model.with_structured_output(output_type)

            messages = []
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            messages.append(HumanMessage(content=user_prompt))

            response = await structured_llm.ainvoke(messages)

            if response is None:
                raise ValueError("LLM返回了空响应")

            logger.info(f"[LangChain-Structured] response: {response}")

            if track_stats:
                in_tokens = calc_input_tokens(system_prompt, user_prompt)
                try:
                    out_text = (
                        response
                        if isinstance(response, str)
                        else json.dumps(response, ensure_ascii=False)
                    )
                except Exception:
                    out_text = str(response)
                out_tokens = estimate_tokens(out_text)
                record_usage(
                    session, llm_config_id,
                    in_tokens, out_tokens,
                    calls=1, aborted=False
                )

            return response

        except asyncio.CancelledError:
            logger.info("[LangChain-Structured] LLM调用被取消（CancelledError），立即中止，不再重试。")
            if track_stats:
                in_tokens = calc_input_tokens(system_prompt, user_prompt)
                record_usage(
                    session, llm_config_id,
                    in_tokens, 0,
                    calls=1, aborted=True
                )
            raise
        except Exception as e:
            last_exception = e
            logger.warning(
                f"[LangChain-Structured] 调用失败，重试 {attempt + 1}/{max_retries}，llm_config_id={llm_config_id}: {e}"
            )

            if attempt < max_retries - 1:
                retry_delay = min(2 ** attempt, 4)
                logger.info(f"[LangChain-Structured] 等待 {retry_delay} 秒后重试...")
                await asyncio.sleep(retry_delay)

    logger.error(
        f"[LangChain-Structured] 调用在重试 {max_retries} 次后仍失败，llm_config_id={llm_config_id}. Last error: {last_exception}"
    )
    raise ValueError(
        f"调用LLM服务失败，已重试 {max_retries} 次: {str(last_exception)}"
    )


async def generate_continuation_streaming(
    session: Session,
    request: ContinuationRequest,
    system_prompt: str,
    track_stats: bool = True
) -> AsyncGenerator[str, None]:
    """续写流式生成
    
    Args:
        session: 数据库会话
        request: 续写请求对象
        system_prompt: 系统提示词（由外部传入）
        track_stats: 是否记录统计
        
    Yields:
        生成的文本片段
    """
    # 组装用户消息
    user_prompt_parts = []
    
    # 1. 添加上下文信息（引用上下文 + 事实子图）
    context_info = (getattr(request, 'context_info', None) or '').strip()
    if context_info:
        # 检测context_info是否已包含结构化标记
        has_structured_marks = any(
            mark in context_info 
            for mark in ['【引用上下文】', '【上文】', '【需要润色', '【需要扩写']
        )
        
        if has_structured_marks:
            # 已经是结构化的上下文，直接使用
            user_prompt_parts.append(context_info)
        else:
            # 未结构化的上下文（老格式），添加标记
            user_prompt_parts.append(f"【参考上下文】\n{context_info}")
    
    # 2. 添加已有章节内容（仅当previous_content非空时）
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
        # 新写模式或润色/扩写模式（previous_content为空）
        if getattr(request, 'append_continuous_novel_directive', True):
            if context_info and '【已有章节内容】' in context_info:
                user_prompt_parts.append("【指令】请接着上述内容继续写作，保持文风和剧情连贯。直接输出小说正文。")
            else:
                user_prompt_parts.append("【指令】请开始创作新章节。直接输出小说正文。")
    
    user_prompt = "\n\n".join(user_prompt_parts)
    
    # 限额预检
    if track_stats:
        ok, reason = precheck_quota(
            session, request.llm_config_id,
            calc_input_tokens(system_prompt, user_prompt),
            need_calls=1
        )
        if not ok:
            raise ValueError(f"LLM配额不足: {reason}")

    # 使用LangChain ChatModel进行流式续写
    model = build_chat_model(
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
        logger.debug("正在以LangChain ChatModel流式生成续写内容")
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
        logger.info("流式LLM调用被取消（CancelledError），停止推送。")
        if track_stats:
            in_tokens = calc_input_tokens(system_prompt, user_prompt)
            out_tokens = estimate_tokens(accumulated)
            record_usage(
                session, request.llm_config_id,
                in_tokens, out_tokens,
                calls=1, aborted=True
            )
        return
    except Exception as e:
        logger.error(f"流式LLM调用失败: {e}")
        raise

    # 正常结束后统计
    try:
        if track_stats:
            in_tokens = calc_input_tokens(system_prompt, user_prompt)
            out_tokens = estimate_tokens(accumulated)
            record_usage(
                session, request.llm_config_id,
                in_tokens, out_tokens,
                calls=1, aborted=False
            )
    except Exception as stat_e:
        logger.warning(f"记录LLM流式统计失败: {stat_e}")
