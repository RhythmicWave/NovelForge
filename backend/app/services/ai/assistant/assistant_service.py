"""灵感助手服务

提供基于LangChain的工具调用和流式对话功能。
"""

from typing import Any, Dict, AsyncGenerator, Optional, Tuple
import asyncio
import json
import re

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

from app.schemas.ai import AssistantChatRequest
from .tools import (
    AssistantDeps,
    ASSISTANT_TOOLS,
    ASSISTANT_TOOL_REGISTRY,
    ASSISTANT_TOOL_DESCRIPTIONS,
    set_assistant_deps,
)
from app.services.ai.core.llm_service import build_chat_model
from app.services.ai.core.token_utils import calc_input_tokens, estimate_tokens
from app.services.ai.core.quota_manager import precheck_quota, record_usage


# React文本协议相关正则
_ACTION_TAG_RE = re.compile(r"<Action>(.*?)</Action>", re.IGNORECASE | re.DOTALL)
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_JSON_BLOCK_RE = re.compile(r"Action\s*:?\s*(\{.*\})", re.IGNORECASE | re.DOTALL)
_PROTOCOL_TAGS = ("action",)

MAX_REACT_STEPS = 100


def _extract_first(pattern: re.Pattern, text: str) -> Optional[str]:
    """提取正则匹配的第一个结果"""
    if not text:
        return None
    m = pattern.search(text)
    if not m:
        return None
    return (m.group(1) or "").strip()


def _clean_code_fence(block: str) -> str:
    """清理代码块标记"""
    if not block:
        return ""
    fence = _CODE_FENCE_RE.search(block)
    if fence:
        return fence.group(1).strip()
    return block.strip()


def _parse_action_payload(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """解析Action标签中的工具调用信息"""
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
            logger.debug(f"[React Parser] JSON解析失败: {cleaned}")
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
            logger.debug(f"[React Parser] 工具参数无法转换为dict: {args}")
            return None

    return tool_name.strip(), args


def _process_react_stream_text(state: dict[str, str], new_text: str) -> str:
    """在流式阶段移除协议标签，保留换行符和空白字符以维护Markdown格式"""
    buffer = state.get("buffer", "") + (new_text or "")
    output_parts: list[str] = []

    while buffer:
        tag_start = buffer.find("<")
        
        if tag_start == -1:
            output_parts.append(buffer)
            buffer = ""
            break
            
        if tag_start > 0:
            output_parts.append(buffer[:tag_start])
            buffer = buffer[tag_start:]
            
        lower = buffer.lower()
        
        potential_tag = None
        for tag in _PROTOCOL_TAGS:
            prefix = f"<{tag}"
            
            if lower.startswith(prefix):
                potential_tag = tag
                break
            if len(buffer) < len(prefix) and prefix.startswith(lower):
                state["buffer"] = buffer
                return "".join(output_parts)

        if not potential_tag:
            output_parts.append("<")
            buffer = buffer[1:]
            continue
            
        close_token = f"</{potential_tag}>"
        close_idx = lower.find(close_token)
        
        if close_idx == -1:
            state["buffer"] = buffer
            return "".join(output_parts)
            
        block_end = close_idx + len(close_token)
        block = buffer[:block_end]
        
        inner_start = block.find(">")
        if inner_start == -1:
            state["buffer"] = buffer
            return "".join(output_parts)
             
        _ = block[inner_start + 1 : close_idx]
        buffer = buffer[block_end:]

    state["buffer"] = buffer
    return "".join(output_parts)


def _flush_react_stream_state(state: dict[str, str]) -> str:
    """在对话结束前清空缓冲，防止残留协议文本"""
    buffer = state.get("buffer", "")
    state["buffer"] = ""
    if not buffer:
        return ""
    return _process_react_stream_text(state, "")


def _render_tool_catalog() -> str:
    """渲染工具目录"""
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
    """格式化React模式的用户提示词"""
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
    """在当前事件循环线程中直接调用工具"""
    tool = ASSISTANT_TOOL_REGISTRY.get(tool_name)
    if not tool:
        raise ValueError(f"未知工具: {tool_name}")

    try:
        logger.info(
            "[Assistant-Tool][React] 调用工具 %s, args=%s",
            tool_name,
            json.dumps(args or {}, ensure_ascii=False, default=str),
        )
        result = tool.invoke(args or {})

        try:
            preview = json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            preview = str(result)
        logger.info(
            "[Assistant-Tool][React] 工具 %s 调用完成, result_preview=%s",
            tool_name,
            preview[:500],
        )
        return result
    except Exception as e:
        logger.exception("[Assistant-Tool][React] 工具 %s 调用失败: %s", tool_name, e)
        raise


def _extract_chunk_parts(chunk: AIMessageChunk) -> Tuple[str, list[str]]:
    """从AIMessageChunk中提取文本和推理内容"""
    reasoning_segments: list[str] = []
    
    # 1. 尝试从additional_kwargs提取reasoning_content (DeepSeek/OpenAI兼容)
    kwargs = getattr(chunk, "additional_kwargs", {})
    if kwargs:
        r_content = kwargs.get("reasoning_content")
        if r_content and isinstance(r_content, str):
            reasoning_segments.append(r_content)
            
    # 2. 尝试从standard content list提取
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
    """将chunk转换为AIMessage"""
    if chunk is None:
        return AIMessage(content=fallback_text)
    try:
        return chunk.to_message()
    except Exception:
        return AIMessage(content=fallback_text)


def _extract_usage_from_chunk(chunk: AIMessageChunk) -> Tuple[int, int]:
    """从chunk中提取token使用量"""
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


async def stream_chat_with_react(
    session: Session,
    request: AssistantChatRequest,
    system_prompt: str,
) -> AsyncGenerator[dict, None]:
    """文本版React工具协议：LLM用文字声明Action，系统解析并调用工具"""
    final_user_prompt = _format_react_user_prompt(
        request.context_info or "",
        request.user_prompt or "",
    )

    logger.info(f"[React-Agent] system_prompt: {system_prompt[:200]}...")
    logger.info(f"[React-Agent] user_prompt: {final_user_prompt[:200]}...")

    ok, reason = precheck_quota(
        session,
        request.llm_config_id,
        calc_input_tokens(system_prompt, final_user_prompt),
        need_calls=1,
    )
    if not ok:
        raise ValueError(f"LLM配额不足: {reason}")

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
            has_visible_text = False
            stream_state: dict[str, str] = {"buffer": ""}

            async for chunk in model.astream(messages):
                if not isinstance(chunk, AIMessageChunk):
                    continue
                delta_text, delta_reasonings = _extract_chunk_parts(chunk)

                if delta_text:
                    step_text += delta_text

                # 处理reasoning内容
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

            # 从本轮累计的文本中解析Action协议
            action_payload = _parse_action_payload(step_text)

            if action_payload:
                tool_name, args = action_payload
                logger.info(
                    "[React-Agent] 解析到Action: tool=%s, args=%s",
                    tool_name,
                    json.dumps(args or {}, ensure_ascii=False, default=str),
                )
                yield {
                    "type": "tool_start",
                    "data": {"tool_name": tool_name, "args": args},
                }
                try:
                    set_assistant_deps(deps)
                    logger.info("[React-Agent] 开始执行工具 %s", tool_name)
                    result = await _invoke_assistant_tool(tool_name, args)
                    success = True
                    logger.info("[React-Agent] 工具 %s 执行结束, success=%s", tool_name, success)
                except Exception as tool_err:
                    logger.exception("[React-Agent] 工具 %s 执行异常: %s", tool_name, tool_err)
                    result = {"success": False, "error": str(tool_err)}
                    success = False
                # 使用HumanMessage传递工具结果
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
            raise RuntimeError("React模式达到最大思考轮数仍未结束")

        if not completed:
            raise RuntimeError("React模式未能产生最终回复")

    except asyncio.CancelledError:
        logger.warning(f"[React-Agent] 请求被客户端取消 (CancelledError)")
        if usage_in_total and usage_out_total:
            in_tokens = usage_in_total
            out_tokens = usage_out_total
        else:
            in_tokens = calc_input_tokens(system_prompt, final_user_prompt)
            out_tokens = estimate_tokens(accumulated_text + reasoning_accumulated)
        record_usage(
            session,
            request.llm_config_id,
            in_tokens,
            out_tokens,
            calls=1,
            aborted=True,
        )
        raise
    except Exception as e:
        logger.error(f"[React-Agent] 执行失败: {e}")
        raise

    in_tokens = usage_in_total or calc_input_tokens(system_prompt, final_user_prompt)
    out_tokens = usage_out_total or estimate_tokens(accumulated_text + reasoning_accumulated)
    record_usage(
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
    """基于LangChain的助手工具调用（ReAct风格智能体）
    
    使用LangChain 1.x文档推荐的create_agent + agent.astream实现工具调用。
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

    ok, reason = precheck_quota(
        session,
        request.llm_config_id,
        calc_input_tokens(system_prompt, final_user_prompt),
        need_calls=1,
    )
    if not ok:
        raise ValueError(f"LLM配额不足: {reason}")

    # 构造底层ChatModel
    model = build_chat_model(
        session=session,
        llm_config_id=request.llm_config_id,
        temperature=request.temperature or 0.6,
        max_tokens=request.max_tokens or 8192,
        timeout=request.timeout or 90,
        thinking_enabled=getattr(request, "thinking_enabled", None),
    )

    # 为当前请求注入依赖
    deps = AssistantDeps(session=session, project_id=request.project_id)
    set_assistant_deps(deps)

    tools = ASSISTANT_TOOLS

    # 构造中间件列表
    middleware = []
    if getattr(request, "context_summarization_enabled", None):
        max_tokens_before_summary = (
            int(request.context_summarization_threshold)
            if getattr(request, "context_summarization_threshold", None)
            else 8192
        )
        try:
            middleware.append(
                SummarizationMiddleware(
                    model=model,
                    max_tokens_before_summary=max_tokens_before_summary,
                )
            )
        except Exception as e:
            logger.warning(f"初始化SummarizationMiddleware失败，将忽略上下文摘要: {e}")

    # 使用LangChain 1.x的create_agent创建带工具的智能体
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware,
    )

    accumulated_text = ""
    reasoning_accumulated = ""
    usage_input_tokens: Optional[int] = None
    usage_output_tokens: Optional[int] = None

    try:
        # 同时流式传输代理进度（updates）和LLM token（messages）
        async for stream_mode, chunk in agent.astream(
            {
                "messages": [
                    {"role": "user", "content": final_user_prompt},
                ]
            },
            stream_mode=["updates", "messages"],
        ):
            # 处理工具调用相关事件（来自updates流）
            if stream_mode == "updates":
                if not isinstance(chunk, dict):
                    continue

                for node, data in chunk.items():
                    messages = (data or {}).get("messages") or []
                    for msg in messages:
                        # 模型节点：包含工具调用信息的AIMessage
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

                        # 工具节点：工具执行结果的ToolMessage
                        if isinstance(msg, ToolMessage):
                            tool_name = getattr(msg, "name", "") or ""

                            raw_content = msg.content
                            result_obj = raw_content

                            if isinstance(raw_content, str):
                                try:
                                    result_obj = json.loads(raw_content)
                                except Exception:
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

            # 处理LLM token（来自messages流）
            if stream_mode == "messages":
                try:
                    token, metadata = chunk
                except Exception:
                    continue

                # 只关心模型节点的输出
                node = (metadata or {}).get("langgraph_node")
                if node != "model":
                    continue

                # 尝试从metadata中读取usage信息
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

                # content_blocks中包含text / reasoning / tool_call_chunk等类型
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
                    # 回退：直接从content取字符串
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

            continue

    except asyncio.CancelledError:
        # 中途取消：仍然记录包括reasoning在内的已生成文本
        if usage_input_tokens is not None and usage_output_tokens is not None:
            in_tokens = usage_input_tokens
            out_tokens = usage_output_tokens
        else:
            in_tokens = calc_input_tokens(system_prompt, final_user_prompt)
            out_tokens = estimate_tokens(accumulated_text + reasoning_accumulated)
        record_usage(
            session,
            request.llm_config_id,
            in_tokens,
            out_tokens,
            calls=1,
            aborted=True,
        )

        if reasoning_accumulated:
            yield {
                "type": "reasoning",
                "data": {"text": reasoning_accumulated},
            }
        return
    except Exception as e:
        logger.error(f"[LangChain+Agent] chat failed: {e}")
        raise

    # 在正常结束时，如果存在reasoning内容，先推送一次供前端折叠展示
    if reasoning_accumulated:
        yield {
            "type": "reasoning",
            "data": {"text": reasoning_accumulated},
        }

    if usage_input_tokens is not None and usage_output_tokens is not None:
        in_tokens = usage_input_tokens
        out_tokens = usage_output_tokens
    else:
        in_tokens = calc_input_tokens(system_prompt, final_user_prompt)
        out_tokens = estimate_tokens(accumulated_text + reasoning_accumulated)
    record_usage(
        session,
        request.llm_config_id,
        in_tokens,
        out_tokens,
        calls=1,
        aborted=False,
    )


async def generate_assistant_chat_streaming(
    session: Session,
    request: AssistantChatRequest,
    system_prompt: str,
    track_stats: bool = True
) -> AsyncGenerator[str, None]:
    """灵感助手专用流式对话生成（结构化事件流协议）
    
    当前实现完全基于LangChain ChatModel + LangChain Tools，实现工具调用与事件流：
    - token
    - tool_start
    - tool_end
    
    Args:
        session: 数据库会话
        request: 助手请求对象
        system_prompt: 系统提示词
        track_stats: 是否记录统计
        
    Yields:
        JSON格式的事件字符串
    """
    react_enabled = bool(getattr(request, "react_mode_enabled", False))
    logger.info("[LangChain] generate_assistant_chat_streaming: 使用{}模式".format("React" if react_enabled else "标准"))

    engine = stream_chat_with_react if react_enabled else stream_chat_with_tools

    try:
        async for evt in engine(
            session=session,
            request=request,
            system_prompt=system_prompt,
        ):
            # LangChain分支直接产出事件dict，这里统一转成JSON-line协议
            yield json.dumps(evt, ensure_ascii=False)
    except asyncio.CancelledError:
        logger.info("[LangChain] 助手调用被取消（CancelledError）")
        return
    except Exception as e:
        logger.error(f"[LangChain] 灵感助手生成失败: {e}")
        error_event = {
            "type": "error",
            "data": {"error": str(e)},
        }
        yield json.dumps(error_event, ensure_ascii=False)
        raise
