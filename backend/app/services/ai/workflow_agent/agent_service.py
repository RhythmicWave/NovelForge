from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Dict

from loguru import logger
from sqlmodel import Session

from app.schemas.workflow_agent import WorkflowAgentChatRequest
from app.services import prompt_service
from app.services.workflow import get_all_node_metadata
from app.services.ai.core.react_text_agent import stream_chat_with_react_protocol
from app.services.ai.core.tool_agent_stream import stream_agent_with_tools
from .tools import (
    WORKFLOW_AGENT_TOOL_DESCRIPTIONS,
    WORKFLOW_AGENT_TOOL_REGISTRY,
    WORKFLOW_AGENT_TOOLS,
    WorkflowAgentDeps,
    set_workflow_agent_deps,
)


WORKFLOW_AGENT_PROMPT_NAME = "工作流智能体"
WORKFLOW_AGENT_REACT_PROMPT_NAME = "工作流智能体-React"
WORKFLOW_AGENT_MAX_VALIDATE_RETRIES = 0


def _append_node_briefs_to_prompt(base_prompt: str) -> str:
    """Embed node brief list into system prompt, so agent knows basic node map upfront."""
    try:
        items = get_all_node_metadata() or []
    except Exception as exc:
        logger.warning("[WorkflowAgent] load node briefs failed: {}", exc)
        return base_prompt

    if not items:
        return base_prompt

    lines: list[str] = []
    for item in sorted(items, key=lambda x: (str(getattr(x, "category", "")), str(getattr(x, "type", "")))):
        node_type = str(getattr(item, "type", "") or "").strip()
        if not node_type:
            continue
        label = str(getattr(item, "label", "") or "").strip()
        category = str(getattr(item, "category", "") or "").strip()
        description = str(getattr(item, "description", "") or "").strip()
        line = f"- {node_type} | {label} | {category} | {description}"
        lines.append(line)

    if not lines:
        return base_prompt

    node_map = "\n".join(lines)
    return (
        f"{base_prompt}\n\n"
        "【系统内置节点简表（启动已注入）】\n"
        "你已具备所有节点的简要信息。优先直接根据该简表选节点，仅在需要字段级细节时再调用 wf_get_node_metadata。\n"
        f"{node_map}"
    )




def get_workflow_agent_system_prompt(session: Session, react_enabled: bool = False) -> str:
    """Load Workflow Agent system prompt from Prompt DB only."""
    try:
        prompt = None
        if react_enabled:
            prompt = prompt_service.get_prompt_by_name(session, WORKFLOW_AGENT_REACT_PROMPT_NAME)
            if prompt and prompt.template and prompt.template.strip():
                logger.info(
                    "[WorkflowAgent] loaded system prompt: {}",
                    WORKFLOW_AGENT_REACT_PROMPT_NAME,
                )
                return _append_node_briefs_to_prompt(prompt.template.strip())

            logger.warning(
                "[WorkflowAgent] React mode enabled but prompt not found: {}, fallback to {}",
                WORKFLOW_AGENT_REACT_PROMPT_NAME,
                WORKFLOW_AGENT_PROMPT_NAME,
            )

        prompt = prompt_service.get_prompt_by_name(session, WORKFLOW_AGENT_PROMPT_NAME)
        if prompt and prompt.template and prompt.template.strip():
            logger.info(
                "[WorkflowAgent] loaded system prompt: {}",
                WORKFLOW_AGENT_PROMPT_NAME,
            )
            return _append_node_briefs_to_prompt(prompt.template.strip())
        raise RuntimeError(
            f"未找到提示词: {WORKFLOW_AGENT_PROMPT_NAME}。"
            "请先执行 bootstrap 初始化，或在提示词管理中创建该提示词。"
        )
    except Exception as exc:
        logger.error("[WorkflowAgent] load prompt from DB failed: {}", exc)
        raise RuntimeError(
            f"加载提示词失败: {WORKFLOW_AGENT_PROMPT_NAME}。"
            "请检查数据库与 bootstrap 状态。"
        ) from exc


def _build_user_prompt(request: WorkflowAgentChatRequest) -> str:
    user_prompt = request.user_prompt or ""
    header = (
        f"workflow_id={request.workflow_id}\n"
        f"mode={request.mode.value}\n"
        f"conversation_id={request.conversation_id or ''}"
    )
    pending_code_text = (request.pending_code or "").strip()
    pending_code_section = ""
    if pending_code_text:
        pending_code_section = (
            "\n\n未应用补丁候选代码（优先基于此继续修改，不要先回退到数据库当前代码）:\n"
            f"```python\n{pending_code_text}\n```"
        )

    if user_prompt:
        return f"{header}\n\n用户请求:\n{user_prompt}{pending_code_section}"
    return f"{header}\n\n用户请求为空，请先确认需求并读取当前代码。"


async def stream_workflow_agent_chat(
    session: Session,
    request: WorkflowAgentChatRequest,
    system_prompt: str,
) -> AsyncGenerator[Dict[str, Any], None]:
    history_messages = request.history_messages or []

    def _extract_patch_result(evt: Dict[str, Any]) -> Dict[str, Any] | None:
        if evt.get("type") != "tool_end":
            return None
        data = evt.get("data") or {}
        if not isinstance(data, dict):
            return None
        tool_name = data.get("tool_name")
        if tool_name not in ("wf_apply_patch", "wf_replace_code"):
            return None
        result = data.get("result")
        if isinstance(result, dict):
            return result
        return None

    async def _run_tool_mode_once(user_prompt_text: str):
        final_user_prompt = _build_user_prompt(
            WorkflowAgentChatRequest(
                workflow_id=request.workflow_id,
                llm_config_id=request.llm_config_id,
                user_prompt=user_prompt_text,
                mode=request.mode,
                conversation_id=request.conversation_id,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                timeout=request.timeout,
                thinking_enabled=request.thinking_enabled,
                react_mode_enabled=request.react_mode_enabled,
            )
        )

        async for event in stream_agent_with_tools(
            session=session,
            llm_config_id=request.llm_config_id,
            system_prompt=system_prompt,
            user_prompt=final_user_prompt,
            tools=WORKFLOW_AGENT_TOOLS,
            set_deps=set_workflow_agent_deps,
            deps=WorkflowAgentDeps(session=session, workflow_id=request.workflow_id),
            temperature=request.temperature if request.temperature is not None else 0.4,
            max_tokens=request.max_tokens if request.max_tokens is not None else 4096,
            timeout=request.timeout if request.timeout is not None else 90,
            thinking_enabled=request.thinking_enabled,
            history_messages=history_messages,
            enable_summarization=False,
            max_tokens_before_summary=8192,
            log_tag="WorkflowAgent",
        ):
            yield event

    async def _run_react_mode_once(user_prompt_text: str):
        async for event in stream_chat_with_react_protocol(
            session=session,
            llm_config_id=request.llm_config_id,
            system_prompt=system_prompt,
            context_info=f"workflow_id={request.workflow_id}",
            user_prompt=user_prompt_text,
            tool_registry=WORKFLOW_AGENT_TOOL_REGISTRY,
            tool_descriptions=WORKFLOW_AGENT_TOOL_DESCRIPTIONS,
            set_deps=set_workflow_agent_deps,
            deps=WorkflowAgentDeps(session=session, workflow_id=request.workflow_id),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            timeout=request.timeout,
            thinking_enabled=request.thinking_enabled,
            history_messages=history_messages,
            max_steps=100,
            log_tag="WorkflowAgent-React",
        ):
            yield event

    react_enabled = bool(getattr(request, "react_mode_enabled", False))
    run_once = _run_react_mode_once if react_enabled else _run_tool_mode_once

    latest_prompt = request.user_prompt or ""
    for attempt in range(WORKFLOW_AGENT_MAX_VALIDATE_RETRIES + 1):
        last_patch_failed: bool | None = None
        retry_hint = ""
        saw_patch_tool = False

        async for event in run_once(latest_prompt):
            patch_result = _extract_patch_result(event)
            if patch_result is not None:
                saw_patch_tool = True
                validation = patch_result.get("validation") if isinstance(patch_result, dict) else None
                patch_failed = False
                if isinstance(validation, dict) and "is_valid" in validation:
                    patch_failed = not bool(validation.get("is_valid"))
                elif "success" in patch_result:
                    patch_failed = not bool(patch_result.get("success"))
                else:
                    patch_failed = bool(patch_result.get("error"))

                if patch_failed:
                    validation_errors = []
                    if isinstance(validation, dict):
                        raw_errors = validation.get("errors")
                        if isinstance(raw_errors, list):
                            validation_errors = [str(item) for item in raw_errors[:6]]

                    error_text = patch_result.get("error")
                    if error_text:
                        validation_errors.insert(0, str(error_text))

                    if validation_errors:
                        retry_hint = "；".join(validation_errors)
                    else:
                        retry_hint = "校验未通过"
                else:
                    retry_hint = ""

                last_patch_failed = patch_failed

            yield event

        if not saw_patch_tool:
            logger.warning("[WorkflowAgent] no patch tool called, skip retry")
            break

        if last_patch_failed is not True:
            break

        if attempt >= WORKFLOW_AGENT_MAX_VALIDATE_RETRIES:
            logger.warning(
                "[WorkflowAgent] stop auto-retry after {} attempts, reason={}",
                WORKFLOW_AGENT_MAX_VALIDATE_RETRIES,
                retry_hint,
            )
            break

        latest_prompt = (
            "上一次补丁未通过校验，请继续修复并再次调用工具生成可通过校验的补丁。\n"
            f"失败原因：{retry_hint}"
        )


async def generate_workflow_agent_chat_streaming(
    session: Session,
    request: WorkflowAgentChatRequest,
    system_prompt: str,
) -> AsyncGenerator[str, None]:
    try:
        async for evt in stream_workflow_agent_chat(
            session=session,
            request=request,
            system_prompt=system_prompt,
        ):
            yield json.dumps(evt, ensure_ascii=False)
    except asyncio.CancelledError:
        logger.info("[WorkflowAgent] cancelled")
        return
    except Exception as exc:
        logger.error("[WorkflowAgent] streaming failed: {}", exc)
        error_event = {"type": "error", "data": {"error": str(exc)}}
        yield json.dumps(error_event, ensure_ascii=False)
        return
