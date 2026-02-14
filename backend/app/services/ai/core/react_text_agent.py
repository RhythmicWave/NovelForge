from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncGenerator, Callable, Dict, Mapping, Optional, Sequence, Tuple

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage
from loguru import logger
from sqlmodel import Session

from app.services.ai.core.chat_model_factory import build_chat_model
from app.services.ai.core.quota_manager import precheck_quota, record_usage
from app.services.ai.core.token_utils import calc_input_tokens, estimate_tokens


ACTION_TAG_RE = re.compile(r"<Action>(.*?)</Action>", re.IGNORECASE | re.DOTALL)
CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
JSON_BLOCK_RE = re.compile(r"Action\s*:?\s*(\{.*\})", re.IGNORECASE | re.DOTALL)
PROTOCOL_TAGS = ("action",)


def _extract_first(pattern: re.Pattern, text: str) -> Optional[str]:
    if not text:
        return None
    match = pattern.search(text)
    if not match:
        return None
    return (match.group(1) or "").strip()


def _clean_code_fence(block: str) -> str:
    if not block:
        return ""
    fence = CODE_FENCE_RE.search(block)
    if fence:
        return fence.group(1).strip()
    return block.strip()


def _parse_action_payload(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    if not text:
        return None

    raw_block = _extract_first(ACTION_TAG_RE, text)
    if not raw_block:
        raw_block = _extract_first(JSON_BLOCK_RE, text)
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
            return None

    return tool_name.strip(), args


def _process_react_stream_text(state: dict[str, str], new_text: str) -> str:
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
        for tag in PROTOCOL_TAGS:
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
    buffer = state.get("buffer", "")
    state["buffer"] = ""
    if not buffer:
        return ""
    return _process_react_stream_text(state, "")


def _render_tool_catalog(tool_descriptions: Mapping[str, Any]) -> str:
    lines: list[str] = []
    for name, meta in tool_descriptions.items():
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


def build_react_user_prompt(
    *,
    context_info: str,
    user_prompt: str,
    tool_descriptions: Mapping[str, Any],
) -> str:
    protocol = """
你处于 React-Tool 模式，必须真实调用工具。

工具调用格式（严格）：
<Action>{"tool":"工具名","args":{"参数名":参数值}}</Action>

示例：
<Action>{"tool":"wf_get_current_code","args":{"workflow_id":19}}</Action>

执行规则：
1) 先读代码：先调 wf_get_current_code。
2) 需要改代码时，调用 wf_replace_code 或 wf_apply_patch。
3) 每次改动后必须检查 parse/validation。
4) 若 parse/validation 未通过，继续调用工具修复，直到通过再结束。
5) 不要输出“wf_xxx(...)”伪调用文本替代工具调用。
""".strip()

    parts: list[str] = [protocol]
    if context_info:
        parts.append(f"上下文:\n{context_info}")
    if user_prompt:
        parts.append(f"用户输入:\n{user_prompt}")
    tool_catalog = _render_tool_catalog(tool_descriptions)
    if tool_catalog:
        parts.append("可用工具列表:\n" + tool_catalog)
    return "\n\n".join(parts)


async def _invoke_tool_from_registry(
    tool_registry: Mapping[str, Any],
    tool_name: str,
    args: Dict[str, Any],
    *,
    log_tag: str,
) -> Dict[str, Any]:
    tool = tool_registry.get(tool_name)
    if not tool:
        raise ValueError(f"未知工具: {tool_name}")

    logger.info(
        "[{}] 调用工具 {}, args={}",
        log_tag,
        tool_name,
        json.dumps(args or {}, ensure_ascii=False, default=str),
    )
    result = tool.invoke(args or {})
    return result


def _extract_chunk_parts(chunk: AIMessageChunk) -> Tuple[str, list[str]]:
    reasoning_segments: list[str] = []
    kwargs = getattr(chunk, "additional_kwargs", {})
    if kwargs:
        r_content = kwargs.get("reasoning_content")
        if r_content and isinstance(r_content, str):
            reasoning_segments.append(r_content)

    content = getattr(chunk, "content", None)
    text_parts: list[str] = []
    if isinstance(content, str):
        text_parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type")
                if block_type == "text" and isinstance(block.get("text"), str):
                    text_parts.append(block["text"])
                elif block_type == "reasoning" and isinstance(block.get("text"), str):
                    reasoning_segments.append(block["text"])
            elif isinstance(block, str):
                text_parts.append(block)

    return "".join(text_parts), reasoning_segments


def _chunk_to_message(full_chunk: Optional[AIMessageChunk], fallback_text: str) -> AIMessage:
    if full_chunk is None:
        return AIMessage(content=fallback_text or "")
    try:
        return full_chunk.to_message()
    except Exception:
        return AIMessage(content=fallback_text or "")


def _extract_usage_from_chunk(full_chunk: AIMessageChunk) -> Tuple[int, int]:
    usage = getattr(full_chunk, "usage_metadata", None)
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


async def stream_chat_with_react_protocol(
    *,
    session: Session,
    llm_config_id: int,
    system_prompt: str,
    context_info: str,
    user_prompt: str,
    tool_registry: Mapping[str, Any],
    tool_descriptions: Mapping[str, Any],
    set_deps: Optional[Callable[[Any], None]] = None,
    deps: Any = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
    thinking_enabled: Optional[bool] = None,
    max_steps: int = 100,
    history_messages: Optional[Sequence[dict[str, str]]] = None,
    log_tag: str = "React-Agent",
) -> AsyncGenerator[dict, None]:
    final_user_prompt = build_react_user_prompt(
        context_info=context_info or "",
        user_prompt=user_prompt or "",
        tool_descriptions=tool_descriptions,
    )

    ok, reason = precheck_quota(
        session,
        llm_config_id,
        calc_input_tokens(system_prompt, final_user_prompt),
        need_calls=1,
    )
    if not ok:
        raise ValueError(f"LLM配额不足: {reason}")

    model = build_chat_model(
        session=session,
        llm_config_id=llm_config_id,
        temperature=temperature or 0.6,
        max_tokens=max_tokens,
        timeout=timeout or 90,
        thinking_enabled=thinking_enabled,
    )

    if set_deps is not None:
        set_deps(deps)

    messages: list[Any] = [SystemMessage(content=system_prompt)]

    for item in history_messages or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        text = content.strip()
        if role == "user":
            messages.append(HumanMessage(content=text))
        elif role == "assistant":
            messages.append(AIMessage(content=text))

    messages.append(HumanMessage(content=final_user_prompt))

    accumulated_text = ""
    reasoning_accumulated = ""
    usage_in_total = 0
    usage_out_total = 0

    try:
        completed = False

        for _step in range(max_steps):
            full_chunk: Optional[AIMessageChunk] = None
            step_text = ""
            stream_state: dict[str, str] = {"buffer": ""}

            async for chunk in model.astream(messages):
                if not isinstance(chunk, AIMessageChunk):
                    continue
                delta_text, delta_reasonings = _extract_chunk_parts(chunk)
                if delta_text:
                    step_text += delta_text

                for seg in delta_reasonings or []:
                    if seg:
                        reasoning_accumulated += seg
                        yield {"type": "reasoning", "data": {"text": seg, "delta": True}}

                cleaned_delta = _process_react_stream_text(stream_state, delta_text or "")
                if cleaned_delta:
                    accumulated_text += cleaned_delta
                    yield {"type": "token", "data": {"text": cleaned_delta, "delta": True}}

                if full_chunk is None:
                    full_chunk = chunk
                else:
                    full_chunk = full_chunk + chunk

            tail_text = _flush_react_stream_state(stream_state)
            if tail_text:
                accumulated_text += tail_text
                yield {"type": "token", "data": {"text": tail_text, "delta": True}}

            response = _chunk_to_message(full_chunk, step_text)
            messages.append(response)

            if full_chunk:
                in_tokens, out_tokens = _extract_usage_from_chunk(full_chunk)
                usage_in_total += in_tokens
                usage_out_total += out_tokens

            action_payload = _parse_action_payload(step_text)
            if action_payload:
                tool_name, tool_args = action_payload
                yield {
                    "type": "tool_start",
                    "data": {"tool_name": tool_name, "args": tool_args},
                }

                success = True
                try:
                    tool_result = await _invoke_tool_from_registry(
                        tool_registry,
                        tool_name,
                        tool_args,
                        log_tag=log_tag,
                    )
                except Exception as tool_err:
                    success = False
                    tool_result = {"success": False, "error": str(tool_err)}

                yield {
                    "type": "tool_end",
                    "data": {
                        "tool_name": tool_name,
                        "args": tool_args,
                        "result": tool_result,
                        "success": success,
                    },
                }

                messages.append(
                    HumanMessage(
                        content=f"Observation ({tool_name}):\n{json.dumps(tool_result, ensure_ascii=False)}"
                    )
                )
                continue

            completed = True
            break

        if not completed:
            raise RuntimeError("React模式达到最大思考轮数仍未结束")

    except asyncio.CancelledError:
        in_tokens = usage_in_total or calc_input_tokens(system_prompt, final_user_prompt)
        out_tokens = usage_out_total or estimate_tokens(accumulated_text + reasoning_accumulated)
        record_usage(session, llm_config_id, in_tokens, out_tokens, calls=1, aborted=True)
        raise
    except Exception:
        raise

    in_tokens = usage_in_total or calc_input_tokens(system_prompt, final_user_prompt)
    out_tokens = usage_out_total or estimate_tokens(accumulated_text + reasoning_accumulated)
    record_usage(session, llm_config_id, in_tokens, out_tokens, calls=1, aborted=False)
