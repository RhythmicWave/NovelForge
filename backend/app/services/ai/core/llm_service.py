"""通用LLM服务

提供ChatModel构建、结构化生成和续写功能。
"""

from typing import Type, Optional, AsyncGenerator
from pydantic import BaseModel
from sqlmodel import Session
from loguru import logger
import asyncio
import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_qwq import ChatQwen

from app.db.models import LLMConfig
from app.services import llm_config_service
from app.schemas.ai import ContinuationRequest
from .token_utils import calc_input_tokens, estimate_tokens
from .quota_manager import precheck_quota, record_usage


def _get_llm_config(session: Session, llm_config_id: int) -> LLMConfig:
    """获取LLM配置"""
    cfg = llm_config_service.get_llm_config(session, llm_config_id)
    if not cfg:
        raise ValueError(f"LLM配置不存在，ID: {llm_config_id}")
    if not cfg.api_key:
        raise ValueError(f"未找到LLM配置 {cfg.display_name or cfg.model_name} 的API密钥")
    return cfg


def build_chat_model(
    session: Session,
    llm_config_id: int,
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
    thinking_enabled: Optional[bool] = None,
):
    """构建LangChain ChatModel实例
    
    所有LLM调用的底层入口，不包含业务逻辑。
    
    Args:
        session: 数据库会话
        llm_config_id: LLM配置ID
        temperature: 温度参数
        max_tokens: 最大token数
        timeout: 超时时间（秒）
        thinking_enabled: 是否启用思考模式（部分模型支持）
        
    Returns:
        LangChain ChatModel实例
    """
    cfg = _get_llm_config(session, llm_config_id)
    provider = (cfg.provider or "").lower()

    common_kwargs: dict = {}
    if temperature is not None:
        common_kwargs["temperature"] = float(temperature)
    if max_tokens is not None:
        common_kwargs["max_tokens"] = int(max_tokens)
    if timeout is not None:
        common_kwargs["timeout"] = float(timeout)

    logger.info(
        f"[LangChain] build_chat_model provider={provider}, model={cfg.model_name}, "
        f"temperature={temperature}, max_tokens={max_tokens}, timeout={timeout}"
    )

    # OpenAI兼容（使用ChatQwen以更好支持推理模型）
    if provider == "openai_compatible":
        model_kwargs: dict = {
            "model": cfg.model_name,
            "api_key": cfg.api_key,
        }
        if cfg.api_base:
            model_kwargs["base_url"] = cfg.api_base
        # 根据前端开关控制 thinking 模式
        if thinking_enabled is not None:
            model_kwargs["extra_body"] = {"enable_thinking": thinking_enabled}
        model_kwargs.update(common_kwargs)
        return ChatQwen(**model_kwargs)

    # 原生OpenAI
    if provider == "openai":
        model_kwargs = {
            "model": cfg.model_name,
            "api_key": cfg.api_key,
        }
        model_kwargs.update(common_kwargs)
        return ChatOpenAI(**model_kwargs)

    # Anthropic
    if provider == "anthropic":
        model_kwargs = {
            "model": cfg.model_name,
            "api_key": cfg.api_key,
        }
        # 根据前端开关控制 thinking 模式
        if thinking_enabled is True:
            model_kwargs["thinking"] = {"type": "enabled", "budget_tokens": 2048}
        elif thinking_enabled is False:
            # Anthropic 默认关闭，无需显式设置
            pass
        model_kwargs.update(common_kwargs)
        return ChatAnthropic(**model_kwargs)

    # Google Gemini
    if provider == "google":
        model_kwargs = {
            "model": cfg.model_name,
            "api_key": cfg.api_key,
        }
        # 根据前端开关控制 thinking 模式
        if thinking_enabled is not None:
            model_kwargs["include_thoughts"] = thinking_enabled
        if max_tokens is not None:
            model_kwargs["max_output_tokens"] = int(max_tokens)
            model_kwargs.pop("max_tokens", None)
        if temperature is not None:
            model_kwargs["temperature"] = float(temperature)
        return ChatGoogleGenerativeAI(**model_kwargs)

    raise ValueError(f"不支持的LLM提供商: {cfg.provider}")


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
) -> BaseModel:
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
    # 配额预检
    if track_stats:
        ok, reason = precheck_quota(
            session, llm_config_id,
            calc_input_tokens(system_prompt, user_prompt),
            need_calls=1
        )
        if not ok:
            raise ValueError(f"LLM配额不足: {reason}")

    logger.info(f"[LangChain-Structured] system_prompt: {system_prompt}")
    logger.info(f"[LangChain-Structured] user_prompt: {user_prompt}")

    last_exception = None
    for attempt in range(max_retries):
        try:
            # 构造底层ChatModel
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
                raise ValueError("LLM返回了空响应")

            logger.info(f"[LangChain-Structured] response: {response}")

            # 统计
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
