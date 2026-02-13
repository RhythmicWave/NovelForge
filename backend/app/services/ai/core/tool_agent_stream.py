from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Callable, Optional, Sequence

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from loguru import logger
from sqlmodel import Session

from .agent_builder import build_agent
from .chat_model_factory import build_chat_model
from .quota_manager import precheck_quota, record_usage
from .token_utils import calc_input_tokens, estimate_tokens


async def stream_agent_with_tools(
    *,
    session: Session,
    llm_config_id: int,
    system_prompt: str,
    user_prompt: str,
    tools: Sequence[BaseTool],
    set_deps: Optional[Callable[[Any], None]] = None,
    deps: Any = None,
    temperature: float = 0.6,
    max_tokens: int = 8192,
    timeout: float = 90,
    thinking_enabled: Optional[bool] = None,
    enable_summarization: bool = False,
    max_tokens_before_summary: int = 8192,
    history_messages: Optional[Sequence[dict[str, str]]] = None,
    log_tag: str = "ToolAgent",
) -> AsyncGenerator[dict, None]:
    ok, reason = precheck_quota(
        session,
        llm_config_id,
        calc_input_tokens(system_prompt, user_prompt),
        need_calls=1,
    )
    if not ok:
        raise ValueError(f"LLM配额不足: {reason}")

    model = build_chat_model(
        session=session,
        llm_config_id=llm_config_id,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        thinking_enabled=thinking_enabled,
    )

    if set_deps is not None:
        set_deps(deps)

    agent = build_agent(
        model=model,
        tools=list(tools),
        system_prompt=system_prompt,
        enable_summarization=enable_summarization,
        max_tokens_before_summary=max_tokens_before_summary,
    )

    accumulated_text = ""
    reasoning_accumulated = ""
    usage_input_tokens: Optional[int] = None
    usage_output_tokens: Optional[int] = None

    initial_messages: list[dict[str, str]] = []
    for item in history_messages or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = item.get("content")
        if role not in ("user", "assistant"):
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        initial_messages.append({"role": role, "content": content.strip()})
    initial_messages.append({"role": "user", "content": user_prompt})

    try:
        async for stream_mode, chunk in agent.astream(
            {"messages": initial_messages},
            stream_mode=["updates", "messages"],
        ):
            if stream_mode == "updates":
                if not isinstance(chunk, dict):
                    continue

                for _node, data in chunk.items():
                    messages = (data or {}).get("messages") or []
                    for msg in messages:
                        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                            for tool_call in msg.tool_calls:
                                name = ""
                                args: Any = {}

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

                        if isinstance(msg, ToolMessage):
                            tool_name = getattr(msg, "name", "") or ""

                            raw_content = msg.content
                            result_obj: Any = raw_content
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

            if stream_mode == "messages":
                try:
                    token, metadata = chunk
                except Exception:
                    continue

                node = (metadata or {}).get("langgraph_node")
                if node != "model":
                    continue

                meta = metadata or {}
                if isinstance(meta, dict):
                    usage = (
                        meta.get("usage")
                        or meta.get("token_usage")
                        or meta.get("usage_metadata")
                        or {}
                    )
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

                blocks = getattr(token, "content_blocks", None)
                delta_text = ""
                reasoning_delta = ""

                if isinstance(blocks, list):
                    texts: list[str] = []
                    reasoning_parts: list[str] = []
                    for block in blocks:
                        if not isinstance(block, dict):
                            continue
                        block_type = block.get("type")
                        if block_type == "text":
                            texts.append(block.get("text", ""))
                        elif block_type == "reasoning":
                            reasoning = block.get("reasoning") or block.get("text") or ""
                            if reasoning:
                                reasoning_parts.append(reasoning)
                    delta_text = "".join(texts)
                    reasoning_delta = "".join(reasoning_parts)
                else:
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

    except asyncio.CancelledError:
        if usage_input_tokens is not None and usage_output_tokens is not None:
            in_tokens = usage_input_tokens
            out_tokens = usage_output_tokens
        else:
            in_tokens = calc_input_tokens(system_prompt, user_prompt)
            out_tokens = estimate_tokens(accumulated_text + reasoning_accumulated)

        record_usage(
            session,
            llm_config_id,
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
    except Exception as exc:
        logger.error("[{}] chat failed: {}", log_tag, exc)
        raise

    if reasoning_accumulated:
        yield {
            "type": "reasoning",
            "data": {"text": reasoning_accumulated},
        }

    if usage_input_tokens is not None and usage_output_tokens is not None:
        in_tokens = usage_input_tokens
        out_tokens = usage_output_tokens
    else:
        in_tokens = calc_input_tokens(system_prompt, user_prompt)
        out_tokens = estimate_tokens(accumulated_text + reasoning_accumulated)

    record_usage(
        session,
        llm_config_id,
        in_tokens,
        out_tokens,
        calls=1,
        aborted=False,
    )
