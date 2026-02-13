"""指令流结构化生成运行时。

对外仅暴露与 `llm_service.generate_structured` 对齐的模型入口：
- 输入 `output_type: Type[BaseModel]`
- 输出 `BaseModel`（可选附带 logs）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from loguru import logger
from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from app.services.ai.generation.instruction_generator import generate_instruction_stream
from app.services.ai.generation.instruction_validator import apply_instruction, validate_instruction
from app.services.ai.generation.prompt_builder import build_instruction_system_prompt
from app.services.ai.core.token_utils import calc_input_tokens, estimate_tokens
from app.services.ai.core.quota_manager import precheck_quota, record_usage


async def _run_instruction_flow_with_schema(
    *,
    session: Session,
    llm_config_id: int,
    user_prompt: str,
    schema: Dict[str, Any],
    current_data: Optional[Dict[str, Any]] = None,
    conversation_context: Optional[List[Any]] = None,
    card_prompt: Optional[str] = None,
    system_prompt: Optional[str] = None,
    context_info: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    timeout: float = 150,
    max_retry: int = 3,
    fail_soft: bool = False,
) -> Dict[str, Any]:
    """按 schema 运行指令流并聚合最终结果（内部函数）。

    Returns:
        {
            "data": Dict[str, Any],
            "logs": List[Dict[str, Any]],
        }
    """
    if not isinstance(schema, dict) or not schema:
        raise ValueError("schema 不能为空")

    final_card_prompt = card_prompt if card_prompt is not None else system_prompt
    final_system_prompt = build_instruction_system_prompt(
        session=session,
        schema=schema,
        card_prompt=final_card_prompt,
    )

    assembled_data: Dict[str, Any] = dict(current_data or {})
    logs: List[Dict[str, Any]] = []
    final_data: Optional[Dict[str, Any]] = None

    async for event in generate_instruction_stream(
        session=session,
        llm_config_id=llm_config_id,
        user_prompt=user_prompt,
        system_prompt=final_system_prompt,
        schema=schema,
        current_data=assembled_data,
        conversation_context=conversation_context or [],
        context_info=context_info,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retry=max_retry,
    ):
        event_type = event.get("type")

        if event_type in {"thinking", "warning", "error", "done"}:
            logs.append(event)

        if event_type == "instruction":
            instruction = event.get("instruction")
            if isinstance(instruction, dict):
                try:
                    validate_instruction(instruction, schema)
                    apply_instruction(assembled_data, instruction)
                except Exception as apply_error:
                    logger.debug(f"[InstructionFlowRuntime] 本地应用指令失败: {apply_error}")

        if event_type == "done":
            if not event.get("success"):
                continue

            candidate = event.get("final_data")
            if not isinstance(candidate, dict):
                candidate = assembled_data

            final_data = candidate
            break

    if final_data is None:
        if not fail_soft:
            raise ValueError("指令流未返回可用结果")
        logs.append(
            {
                "type": "warning",
                "text": "指令流未完整结束，已按 fail_soft 返回部分结果",
            }
        )
        final_data = assembled_data

    return {
        "data": final_data,
        "logs": logs,
    }


async def generate_structured_via_instruction_flow_model(
    *,
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
    current_data: Optional[Dict[str, Any]] = None,
    conversation_context: Optional[List[Any]] = None,
    context_info: Optional[str] = None,
    card_prompt: Optional[str] = None,
    fail_soft: bool = False,
    return_logs: bool = False,
) -> BaseModel | Dict[str, Any]:
    """指令流结构化生成（对齐 `generate_structured` 签名）。"""
    del deps

    schema = output_type.model_json_schema(ref_template="#/$defs/{model}")

    final_card_prompt = card_prompt if card_prompt is not None else system_prompt
    final_system_prompt = build_instruction_system_prompt(
        session=session,
        schema=schema,
        card_prompt=final_card_prompt,
    )

    if track_stats:
        ok, reason = precheck_quota(
            session,
            llm_config_id,
            calc_input_tokens(final_system_prompt, user_prompt),
            need_calls=1,
        )
        if not ok:
            raise ValueError(f"LLM配额不足: {reason}")

    generated = await _run_instruction_flow_with_schema(
        session=session,
        llm_config_id=llm_config_id,
        user_prompt=user_prompt,
        schema=schema,
        current_data=current_data,
        conversation_context=conversation_context,
        card_prompt=final_card_prompt,
        system_prompt=final_system_prompt,
        context_info=context_info,
        temperature=temperature if temperature is not None else 0.7,
        max_tokens=max_tokens,
        timeout=timeout if timeout is not None else 150,
        max_retry=max_retries,
        fail_soft=fail_soft,
    )

    data = generated["data"]
    logs = generated["logs"]

    try:
        model_result = output_type.model_validate(data)
    except ValidationError as error:
        if not fail_soft:
            raise ValueError(f"输出模型校验失败: {error}") from error
        logger.warning(f"[InstructionFlowRuntime] fail_soft=1，输出模型未完全通过校验: {error}")
        model_result = output_type.model_construct(**(data if isinstance(data, dict) else {}))

    if track_stats:
        try:
            out_text = model_result.model_dump_json(ensure_ascii=False)
        except Exception:
            out_text = str(model_result)
        record_usage(
            session,
            llm_config_id,
            calc_input_tokens(final_system_prompt, user_prompt),
            estimate_tokens(out_text),
            calls=1,
            aborted=False,
        )

    if return_logs:
        return {
            "result": model_result,
            "logs": logs,
        }

    return model_result
