
from __future__ import annotations

from typing import Any, Dict, AsyncGenerator, Optional, Tuple

import asyncio
import json
import os
import re
import uuid

from loguru import logger
from sqlmodel import Session

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_qwq import ChatQwen

from app.db.models import LLMConfig
from app.schemas.ai import AssistantChatRequest
from app.services import llm_config_service
from app.services.agent_service import (
    _calc_input_tokens,
    _estimate_tokens,
    _record_usage,
    _precheck_quota,
)
from app.services.assistant_tools.ai_tools import (
    AssistantDeps,
    ASSISTANT_TOOLS,
    ASSISTANT_TOOL_REGISTRY,
    ASSISTANT_TOOL_DESCRIPTIONS,
    set_assistant_deps,
)

_ACTION_TAG_RE = re.compile(r"<Action>(.*?)</Action>", re.IGNORECASE | re.DOTALL)
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_JSON_BLOCK_RE = re.compile(r"Action\s*:?\s*(\{.*\})", re.IGNORECASE | re.DOTALL)
# React 文本协议仅保留 Action，一律使用 <Action>{...}</Action> 格式声明工具调用
_PROTOCOL_TAGS = ("action",)

MAX_REACT_STEPS = 8


def _extract_first(pattern: re.Pattern, text: str) -> Optional[str]:
    if not text:
        return None
    m = pattern.search(text)
    if not m:
        return None
    return (m.group(1) or "").strip()


def _clean_code_fence(block: str) -> str:
    if not block:
        return ""
    fence = _CODE_FENCE_RE.search(block)
    if fence:
        return fence.group(1).strip()
    return block.strip()


def _parse_action_payload(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    if not text:
        return None

    raw_block = _extract_first(_ACTION_TAG_RE, text)
    if not raw_block:
        raw_block = _extract_first(_JSON_BLOCK_RE, text)
    if not raw_block:
        return None

    cleaned = _clean_code_fence(raw_block)
    candidate = cleaned
    try:
        data = json.loads(candidate)
    except Exception:
        try:
            candidate = cleaned.replace("'", '"')
            data = json.loads(candidate)
        except Exception:
            logger.debug(f"[React Parser] JSON 解析失败: {cleaned}")
            return None

    if not isinstance(data, dict):
        return None

    tool_name = (
        data.get("tool")
        or data.get("tool_name")
        or data.get("name")
        or data.get("action")
    )

    if not isinstance(tool_name, str) or not tool_name.strip():
        return None

    args = (
        data.get("input")
        or data.get("args")
        or data.get("parameters")
        or {}
    )

    if args is None:
        args = {}

    if not isinstance(args, dict):
        try:
            args = dict(args)
        except Exception:
            logger.debug(f"[React Parser] 工具参数无法转换为 dict: {args}")
            return None

    return tool_name.strip(), args


def _process_react_stream_text(state: dict[str, str], new_text: str) -> str:
    """在流式阶段移除协议标签，但保留换行符和空白字符以维护 Markdown 格式。"""

    buffer = state.get("buffer", "") + (new_text or "")
    output_parts: list[str] = []

    while buffer:
        # 1. 查找最左边的 '<'
        tag_start = buffer.find("<")
        
        # Case A: 没有 '<'，全是安全文本
        if tag_start == -1:
            output_parts.append(buffer)
            buffer = ""
            break
            
        # 先把 '<' 之前的文本输出（保留原始格式）
        if tag_start > 0:
            output_parts.append(buffer[:tag_start])
            buffer = buffer[tag_start:]
            # buffer 现在以 '<' 开头
            
        # 2. 检查这个 '<' 是否是协议标签的开始
        lower = buffer.lower()
        
        potential_tag = None
        for tag in _PROTOCOL_TAGS:
            prefix = f"<{tag}"
            
            if lower.startswith(prefix):
                potential_tag = tag
                break
            # 检查是否是部分匹配（buffer 比标签名短，且完全匹配前缀）
            if len(buffer) < len(prefix) and prefix.startswith(lower):
                # 可能是标签的一部分，等待更多数据
                state["buffer"] = buffer
                return "".join(output_parts)

        # Case B: 看起来完全不是任何已知标签的前缀
        if not potential_tag:
            # 这只是个普通的 '<'，输出它，然后继续处理后面的字符
            output_parts.append("<")
            buffer = buffer[1:]
            continue
            
        # Case C: 确定是某个协议标签（或其前缀）
        close_token = f"</{potential_tag}>"
        close_idx = lower.find(close_token)
        
        if close_idx == -1:
            # 还没收到闭合标签，挂起等待
            state["buffer"] = buffer
            return "".join(output_parts)
            
        # 找到了完整标签块
        block_end = close_idx + len(close_token)
        block = buffer[:block_end]
        
        # 提取内容
        inner_start = block.find(">")
        if inner_start == -1:
            state["buffer"] = buffer
            return "".join(output_parts)
             
        # 提取标签内部内容（目前仅用于完整跳过 <Action> ... </Action>）
        # 注意：这里不直接拼接任何协议标签内部的文本，保证前端只看到清洗后的可见正文。
        _ = block[inner_start + 1 : close_idx]
        
        # 推进 buffer
        buffer = buffer[block_end:]

    state["buffer"] = buffer
    return "".join(output_parts)


def _flush_react_stream_state(state: dict[str, str]) -> str:
    """在对话结束前清空缓冲，防止残留协议文本。"""

    buffer = state.get("buffer", "")
    state["buffer"] = ""
    if not buffer:
        return ""
    return _process_react_stream_text(state, "")


def _render_tool_catalog() -> str:
    lines: list[str] = []
    for name, meta in ASSISTANT_TOOL_DESCRIPTIONS.items():
        desc_raw = meta.get("description") if isinstance(meta, dict) else ""
        desc = (desc_raw or "").strip() or "(无描述)"
        args_meta = meta.get("args") if isinstance(meta, dict) else None
        arg_names: list[str] = []
        if isinstance(args_meta, dict):
            arg_names = [str(key) for key in args_meta.keys()]
        elif isinstance(args_meta, (list, tuple, set)):
            arg_names = [str(item) for item in args_meta]
        elif args_meta:
            arg_names = [str(args_meta)]
        args_text = ", ".join(arg_names) if arg_names else "无参数"
        lines.append(f"- {name}: {desc}（参数: {args_text}）")
    return "\n".join(lines)


def _format_react_user_prompt(context_info: str, user_prompt: str) -> str:
    parts = []
    if context_info:
        parts.append(context_info)
    if user_prompt:
        parts.append(f"用户输入：\n{user_prompt}")
    tool_catalog = _render_tool_catalog()
    if tool_catalog:
        parts.append("可用工具列表：\n" + tool_catalog)
    return "\n\n".join(parts)


async def _invoke_assistant_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """在当前事件循环线程中直接调用工具，避免在线程池中丢失 AssistantDeps。"""

    tool = ASSISTANT_TOOL_REGISTRY.get(tool_name)
    if not tool:
        raise ValueError(f"未知工具: {tool_name}")

    try:
        # 注意：这里是同步调用，工具内部主要是数据库读写，阻塞时间可接受
        logger.info(
            "[Assistant-Tool][React] 调用工具 %s, args=%s",
            tool_name,
            json.dumps(args or {}, ensure_ascii=False, default=str),
        )
        result = tool.invoke(args or {})

        # 结果中可能包含较大 JSON，这里只截断前 500 个字符，避免刷屏
        try:
            preview = json.dumps(result, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001
            preview = str(result)
        logger.info(
            "[Assistant-Tool][React] 工具 %s 调用完成, result_preview=%s",
            tool_name,
            preview[:500],
        )
        return result
    except Exception as e:  # noqa: BLE001
        logger.exception("[Assistant-Tool][React] 工具 %s 调用失败: %s", tool_name, e)
        raise




def _render_response_text(response: AIMessage) -> Tuple[str, list[str]]:
    reasoning_segments: list[str] = []
    if isinstance(response.content, str):
        text = response.content
    elif isinstance(response.content, list):
        texts: list[str] = []
        for part in response.content:
            if isinstance(part, dict):
                p_type = part.get("type")
                if p_type == "reasoning":
                    seg = part.get("reasoning") or part.get("text") or ""
                    if seg:
                        reasoning_segments.append(seg)
                elif p_type == "text":
                    texts.append(part.get("text", ""))
                else:
                    texts.append(part.get("text", ""))
            else:
                texts.append(str(part))
        text = "".join(texts)
    else:
        text = str(response.content)
    return text, reasoning_segments


def _extract_chunk_parts(chunk: AIMessageChunk) -> Tuple[str, list[str]]:
    reasoning_segments: list[str] = []
    
    # 1. 尝试从 additional_kwargs 提取 reasoning_content (DeepSeek/OpenAI 兼容)
    kwargs = getattr(chunk, "additional_kwargs", {})
    if kwargs:
        r_content = kwargs.get("reasoning_content")
        if r_content and isinstance(r_content, str):
            reasoning_segments.append(r_content)
            
    # 2. 尝试从 standard content list 提取
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content, reasoning_segments
    if isinstance(content, list):
        texts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                p_type = part.get("type")
                if p_type == "reasoning":
                    seg = part.get("reasoning") or part.get("text") or ""
                    if seg:
                        reasoning_segments.append(seg)
                elif p_type in {"output_text", "text"}:
                    texts.append(part.get("text", ""))
                else:
                    texts.append(part.get("text", ""))
            else:
                texts.append(str(part))
        return "".join(texts), reasoning_segments
    return str(content or ""), reasoning_segments


def _chunk_to_message(chunk: Optional[AIMessageChunk], fallback_text: str) -> AIMessage:
    if chunk is None:
        return AIMessage(content=fallback_text)
    try:
        return chunk.to_message()
    except Exception:
        return AIMessage(content=fallback_text)


def _extract_usage_from_chunk(chunk: AIMessageChunk) -> Tuple[int, int]:
    usage = getattr(chunk, "usage_metadata", None)
    if not usage:
        meta = getattr(chunk, "response_metadata", None) or {}
        usage = (
            meta.get("usage")
            or meta.get("token_usage")
            or meta.get("usage_metadata")
        )
    if isinstance(usage, dict):
        in_tok = usage.get("input_tokens") or usage.get("input")
        out_tok = usage.get("output_tokens") or usage.get("output")
        try:
            in_tokens = int(in_tok) if in_tok is not None else 0
        except Exception:
            in_tokens = 0
        try:
            out_tokens = int(out_tok) if out_tok is not None else 0
        except Exception:
            out_tokens = 0
        return in_tokens, out_tokens
    return 0, 0


def _get_llm_config(session: Session, llm_config_id: int) -> LLMConfig:
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
    """
    从LLMConfig创建一个LangChain ChatModel。

    只使用一个小而稳定的初始化参数子集来避免版本特定问题。
    """

    cfg = _get_llm_config(session, llm_config_id)
    provider = (cfg.provider or "").lower()

    # Shared kwargs for most providers
    common_kwargs: dict = {}
    if temperature is not None:
        common_kwargs["temperature"] = float(temperature)


    if max_tokens is not None:
        # OpenAI & DeepSeek use max_tokens; Google uses max_output_tokens.
        common_kwargs["max_tokens"] = int(max_tokens)


    if timeout is not None:
        common_kwargs["timeout"] = float(timeout)

    logger.info(
        f"[LangChain] build_chat_model provider={provider}, model={cfg.model_name}, "
        f"temperature={temperature}, max_tokens={max_tokens}, timeout={timeout}"
    )

    # OpenAI 兼容（优先使用 ChatQwen，以更好支持推理模型；原生ChatOpenAI虽然支持各种OpenAI兼容模型，但是似乎对推理支持不好）
    if provider == "openai_compatible":
        model_kwargs: dict = {
            "model": cfg.model_name,
            "api_key": cfg.api_key,
        }
        if cfg.api_base:
            model_kwargs["base_url"] = cfg.api_base
        if thinking_enabled:
            model_kwargs["extra_body"] = {"enable_thinking": True}
        model_kwargs.update(common_kwargs)
        return ChatQwen(**model_kwargs)

    # 原生 OpenAI
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
        # 可选：启用思考过程（Thinking）
        if thinking_enabled:
            model_kwargs["thinking"] = {"type": "enabled", "budget_tokens": 2048}
        model_kwargs.update(common_kwargs)
        return ChatAnthropic(**model_kwargs)

    # Google Gemini via langchain-google-genai
    if provider == "google":
        model_kwargs = {
            "model": cfg.model_name,
            "api_key": cfg.api_key,
        }
        # 可选：启用思考过程（Gemini 的 include_thoughts 开关）
        if thinking_enabled:
            model_kwargs["include_thoughts"] = True
        if max_tokens is not None:
            # Google uses max_output_tokens instead of max_tokens
            model_kwargs["max_output_tokens"] = int(max_tokens)
            model_kwargs.pop("max_tokens", None)
        if temperature is not None:
            model_kwargs["temperature"] = float(temperature)
        return ChatGoogleGenerativeAI(**model_kwargs)

    raise ValueError(f"不支持的 LLM 提供商: {cfg.provider}")




async def stream_chat_with_react(
    session: Session,
    request: AssistantChatRequest,
    system_prompt: str,
) -> AsyncGenerator[dict, None]:
    """文本版 React 工具协议：LLM 用文字声明 Action，系统解析并调用工具。"""

    final_user_prompt = _format_react_user_prompt(
        request.context_info or "",
        request.user_prompt or "",
    )

    logger.info(f"[React-Agent] system_prompt: {system_prompt[:200]}...")
    logger.info(f"[React-Agent] user_prompt: {final_user_prompt[:200]}...")

    ok, reason = _precheck_quota(
        session,
        request.llm_config_id,
        _calc_input_tokens(system_prompt, final_user_prompt),
        need_calls=1,
    )
    if not ok:
        raise ValueError(f"LLM 配额不足:{reason}")

    model = build_chat_model(
        session=session,
        llm_config_id=request.llm_config_id,
        temperature=request.temperature or 0.6,
        max_tokens=request.max_tokens or 8192,
        timeout=request.timeout or 90,
        thinking_enabled=getattr(request, "thinking_enabled", None),
    )

    deps = AssistantDeps(session=session, project_id=request.project_id)
    set_assistant_deps(deps)

    messages: list[Any] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=final_user_prompt),
    ]

    accumulated_text = ""
    reasoning_accumulated = ""

    usage_in_total = 0
    usage_out_total = 0

    try:
        completed = False
    
        for step in range(MAX_REACT_STEPS):
            full_chunk: Optional[AIMessageChunk] = None
            step_text = ""
            # 标记本轮是否已经向用户输出过可见正文文本（FinalAnswer 部分），
            # 只有在输出过正文后才允许解析 <Action>{...}</Action> 并触发工具调用。
            has_visible_text = False
            stream_state: dict[str, str] = {"buffer": ""}

            async for chunk in model.astream(messages):
                if not isinstance(chunk, AIMessageChunk):
                    continue
                delta_text, delta_reasonings = _extract_chunk_parts(chunk)

                if delta_text:
                    step_text += delta_text

                # 处理 reasoning 内容（来自 content_blocks，与标准模式一致）
                for seg in delta_reasonings or []:
                    if seg:
                        reasoning_accumulated += seg
                        yield {
                            "type": "reasoning",
                            "data": {"text": seg, "delta": True},
                        }

                # 清理协议标签后发送文本
                cleaned_delta = _process_react_stream_text(
                    stream_state,
                    delta_text or "",
                )

                if cleaned_delta:
                    has_visible_text = True
                    accumulated_text += cleaned_delta
                    yield {
                        "type": "token",
                        "data": {"text": cleaned_delta, "delta": True},
                    }

                if full_chunk is None:
                    full_chunk = chunk
                else:
                    full_chunk = full_chunk + chunk

            tail_text = _flush_react_stream_state(stream_state)
            if tail_text:
                has_visible_text = True
                accumulated_text += tail_text
                yield {
                    "type": "token",
                    "data": {"text": tail_text, "delta": True},
                }

            response = _chunk_to_message(full_chunk, step_text)
            messages.append(response)

            if full_chunk:
                in_tokens, out_tokens = _extract_usage_from_chunk(full_chunk)
                usage_in_total += in_tokens
                usage_out_total += out_tokens

            # 直接从本轮累计的文本中解析 Action 协议。
            # 早期实现曾经要求 has_visible_text 才允许解析，为的是避免模型在纯思考阶段输出 <Action>。
            # 但在当前提示词下，我们只约定了 <Action>{...}</Action>，没有显式的 Thought/FinalAnswer 标签，
            # 严格依赖 has_visible_text 会导致"只输出 Action、不输出正文"的情况完全被忽略，前端看到的是空回复。
            # 因此这里放宽限制：总是尝试从 step_text 中解析 Action，由上游提示词约束模型行为。
            action_payload = _parse_action_payload(step_text)

            if action_payload:
                tool_name, args = action_payload
                logger.info(
                    "[React-Agent] 解析到 Action: tool=%s, args=%s",
                    tool_name,
                    json.dumps(args or {}, ensure_ascii=False, default=str),
                )
                yield {
                    "type": "tool_start",
                    "data": {"tool_name": tool_name, "args": args},
                }
                try:
                    # 确保工具调用时 deps 仍然可用
                    set_assistant_deps(deps)
                    logger.info("[React-Agent] 开始执行工具 %s", tool_name)
                    result = await _invoke_assistant_tool(tool_name, args)
                    success = True
                    logger.info("[React-Agent] 工具 %s 执行结束, success=%s", tool_name, success)
                except Exception as tool_err:  # noqa: BLE001
                    logger.exception("[React-Agent] 工具 %s 执行异常: %s", tool_name, tool_err)
                    result = {"success": False, "error": str(tool_err)}
                    success = False
                # 使用 HumanMessage 传递工具结果，避免某些模型不支持 ToolMessage
                observation_text = f"Observation: {json.dumps(result, ensure_ascii=False, default=str)}"
                messages.append(HumanMessage(content=observation_text))
                yield {
                    "type": "tool_end",
                    "data": {
                        "tool_name": tool_name,
                        "args": args,
                        "result": result,
                        "success": success,
                    },
                }
                continue

            # 无工具调用，结束会话
            completed = True
            break
        else:
            raise RuntimeError("React 模式达到最大思考轮数仍未结束")

        if not completed:
            raise RuntimeError("React 模式未能产生最终回复")

    except asyncio.CancelledError:
        logger.warning(f"[React-Agent] 请求被客户端取消 (CancelledError)")
        if usage_in_total and usage_out_total:
            in_tokens = usage_in_total
            out_tokens = usage_out_total
        else:
            in_tokens = _calc_input_tokens(system_prompt, final_user_prompt)
            out_tokens = _estimate_tokens(accumulated_text + reasoning_accumulated)
        _record_usage(
            session,
            request.llm_config_id,
            in_tokens,
            out_tokens,
            calls=1,
            aborted=True,
        )
        # 必须重新抛出 CancelledError 以便上层协程正确感知取消
        raise
    except Exception as e:
        logger.error(f"[React-Agent] 执行失败: {e}")
        raise

    in_tokens = usage_in_total or _calc_input_tokens(system_prompt, final_user_prompt)
    out_tokens = usage_out_total or _estimate_tokens(accumulated_text + reasoning_accumulated)
    _record_usage(
        session,
        request.llm_config_id,
        in_tokens,
        out_tokens,
        calls=1,
        aborted=False,
    )
async def stream_chat_with_tools(
    session: Session,
    request: AssistantChatRequest,
    system_prompt: str,
) -> AsyncGenerator[dict, None]:
    """LangChain-based assistant with tool calling (ReAct-style agent).

    使用 LangChain 1.x 文档推荐的 create_agent + agent.astream 实现工具调用：
      - create_agent(model=model, tools=tools, system_prompt=system_prompt)
      - agent.astream(..., stream_mode=["updates", "messages"])

    事件统一转换为前端使用的协议：
      - token: 模型增量文本
      - tool_start: 工具调用开始
      - tool_end: 工具调用结束（含结果）
    """

    parts: list[str] = []
    if request.context_info:
        parts.append(request.context_info)
    if request.user_prompt:
        parts.append("\nUser: " + request.user_prompt)
    final_user_prompt = "\n\n".join(parts) if parts else "（用户未输入文字，可能是想查看项目信息或需要帮助）"

    logger.info(f"[LangChain+Agent] system_prompt: {system_prompt[:200]}...")
    logger.info(f"[LangChain+Agent] final_user_prompt: {final_user_prompt[:200]}...")

    ok, reason = _precheck_quota(
        session,
        request.llm_config_id,
        _calc_input_tokens(system_prompt, final_user_prompt),
        need_calls=1,
    )
    if not ok:
        raise ValueError(f"LLM 配额不足:{reason}")

    # 构造底层 ChatModel
    model = build_chat_model(
        session=session,
        llm_config_id=request.llm_config_id,
        temperature=request.temperature or 0.6,
        max_tokens=request.max_tokens or 8192,
        timeout=request.timeout or 90,
        thinking_enabled=getattr(request, "thinking_enabled", None),
    )

    # 为当前请求注入依赖，使 LangChain 工具可以通过 ContextVar 访问 session/project_id。
    deps = AssistantDeps(session=session, project_id=request.project_id)
    set_assistant_deps(deps)

    tools = ASSISTANT_TOOLS

    # 构造中间件列表（目前仅支持可选的摘要中间件）
    middleware = []
    # 若前端开启了上下文摘要功能，则挂载 SummarizationMiddleware
    if getattr(request, "context_summarization_enabled", None):
        # 若前端未指定阈值，则采用一个安全的默认值（例如 8192 tokens）
        max_tokens_before_summary = (
            int(request.context_summarization_threshold)
            if getattr(request, "context_summarization_threshold", None)
            else 8192
        )
        try:
            middleware.append(
                SummarizationMiddleware(
                    # 使用当前模型本身生成摘要，避免额外配置第二个模型
                    model=model,
                    max_tokens_before_summary=max_tokens_before_summary,
                )
            )
        except Exception as e:
            logger.warning(f"初始化 SummarizationMiddleware 失败，将忽略上下文摘要: {e}")

    # 使用 LangChain 1.x 的 create_agent 创建带工具的智能体，并按需挂载中间件
    # 注意：LangChain 在内部会直接遍历 middleware，因此这里即使没有中间件也传空列表，避免传入 None
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware,
    )

    accumulated_text = ""
    reasoning_accumulated = ""
    # 若底层提供商支持，优先从 LangChain 返回的 usage 元数据中读取 token 消耗
    usage_input_tokens: Optional[int] = None
    usage_output_tokens: Optional[int] = None

    try:
        # 同时流式传输代理进度（updates）和 LLM token（messages）
        async for stream_mode, chunk in agent.astream(
            {
                "messages": [
                    {"role": "user", "content": final_user_prompt},
                ]
            },
            stream_mode=["updates", "messages"],
        ):
            # 处理工具调用相关事件（来自 updates 流）
            if stream_mode == "updates":
                if not isinstance(chunk, dict):
                    continue

                for node, data in chunk.items():
                    messages = (data or {}).get("messages") or []
                    for msg in messages:
                        # 模型节点：包含工具调用信息的 AIMessage
                        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                            for tool_call in msg.tool_calls:
                                name = ""
                                args = {}

                                if isinstance(tool_call, dict):
                                    name = tool_call.get("name") or ""
                                    args = tool_call.get("args") or {}
                                else:
                                    name = getattr(tool_call, "name", "") or ""
                                    args = getattr(tool_call, "args", {}) or {}

                                if isinstance(args, str):
                                    try:
                                        args = json.loads(args)
                                    except Exception:
                                        args = {"raw": args}

                                if not isinstance(args, dict):
                                    try:
                                        args = dict(args)
                                    except Exception:
                                        args = json.loads(json.dumps(args, ensure_ascii=False))

                                yield {
                                    "type": "tool_start",
                                    "data": {"tool_name": name, "args": args},
                                }

                        # 工具节点：工具执行结果的 ToolMessage
                        if isinstance(msg, ToolMessage):
                            tool_name = getattr(msg, "name", "") or ""

                            # LangChain 通常会将工具返回值序列化为字符串内容。
                            # 为了兼容旧的前端逻辑，这里尽量还原为 dict：
                            raw_content = msg.content
                            result_obj = raw_content

                            if isinstance(raw_content, str):
                                try:
                                    # 优先按 JSON 解析，工具本身返回的就是 dict
                                    result_obj = json.loads(raw_content)
                                except Exception:
                                    # 解析失败则包装在 raw 字段中，避免破坏字符串信息
                                    result_obj = {"raw": raw_content}

                            yield {
                                "type": "tool_end",
                                "data": {
                                    "tool_name": tool_name,
                                    "args": {},
                                    "result": result_obj,
                                },
                            }

                continue

            # 处理 LLM token（来自 messages 流）
            if stream_mode == "messages":
                try:
                    token, metadata = chunk
                except Exception:
                    continue

                # 只关心模型节点的输出（忽略工具节点的纯文本）
                node = (metadata or {}).get("langgraph_node")
                if node != "model":
                    continue

                # 尝试从 metadata 中读取 usage 信息（不同集成字段名可能不同）
                meta = metadata or {}
                if isinstance(meta, dict):
                    try:
                        usage = (
                            meta.get("usage")
                            or meta.get("token_usage")
                            or meta.get("usage_metadata")
                            or {}
                        )
                    except Exception:
                        usage = {}
                    if isinstance(usage, dict):
                        in_tok = usage.get("input_tokens") or usage.get("input")
                        out_tok = usage.get("output_tokens") or usage.get("output")
                        if in_tok is not None:
                            try:
                                usage_input_tokens = int(in_tok)
                            except Exception:
                                pass
                        if out_tok is not None:
                            try:
                                usage_output_tokens = int(out_tok)
                            except Exception:
                                pass

                # content_blocks 中包含 text / reasoning / tool_call_chunk 等类型：
                # - text: 正常展示给用户
                # - reasoning: 仅用于 thinking 展示，不直接拼进助手回复文本
                blocks = getattr(token, "content_blocks", None)
                delta_text = ""
                reasoning_delta = ""

                if isinstance(blocks, list):
                    texts: list[str] = []
                    reasoning_parts: list[str] = []
                    for b in blocks:
                        if not isinstance(b, dict):
                            continue
                        b_type = b.get("type")
                        if b_type == "text":
                            texts.append(b.get("text", ""))
                        elif b_type == "reasoning":
                            r = (
                                b.get("reasoning")
                                or b.get("text")
                                or ""
                            )
                            if r:
                                reasoning_parts.append(r)
                    delta_text = "".join(texts)
                    reasoning_delta = "".join(reasoning_parts)
                else:
                    # 回退：直接从 content 取字符串（不支持 reasoning 分块的旧模型）
                    content = getattr(token, "content", None)
                    if isinstance(content, str):
                        delta_text = content

                if reasoning_delta:
                    reasoning_accumulated += reasoning_delta
                    yield {
                        "type": "reasoning",
                        "data": {"text": reasoning_delta, "delta": True},
                    }

                if delta_text:
                    accumulated_text += delta_text
                    yield {
                        "type": "token",
                        "data": {"text": delta_text, "delta": True},
                    }

                continue

            # 其他流模式忽略
            continue

    except asyncio.CancelledError:
        # 中途取消：仍然记录包括 reasoning 在内的已生成文本
        if usage_input_tokens is not None and usage_output_tokens is not None:
            in_tokens = usage_input_tokens
            out_tokens = usage_output_tokens
        else:
            in_tokens = _calc_input_tokens(system_prompt, final_user_prompt)
            out_tokens = _estimate_tokens(accumulated_text + reasoning_accumulated)
        _record_usage(
            session,
            request.llm_config_id,
            in_tokens,
            out_tokens,
            calls=1,
            aborted=True,
        )

        # 若已生成部分 reasoning 内容，也尝试推送一次供前端展示
        if reasoning_accumulated:
            yield {
                "type": "reasoning",
                "data": {"text": reasoning_accumulated},
            }
        return
    except Exception as e:
        logger.error(f"[LangChain+Agent] chat failed: {e}")
        raise

    # 在正常结束时，如果存在 reasoning 内容，先推送一次供前端折叠展示
    if reasoning_accumulated:
        yield {
            "type": "reasoning",
            "data": {"text": reasoning_accumulated},
        }

    if usage_input_tokens is not None and usage_output_tokens is not None:
        in_tokens = usage_input_tokens
        out_tokens = usage_output_tokens
    else:
        in_tokens = _calc_input_tokens(system_prompt, final_user_prompt)
        out_tokens = _estimate_tokens(accumulated_text + reasoning_accumulated)
    _record_usage(
        session,
        request.llm_config_id,
        in_tokens,
        out_tokens,
        calls=1,
        aborted=False,
    )
