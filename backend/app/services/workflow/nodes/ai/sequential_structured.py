
import copy
import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional, TYPE_CHECKING, Union

from loguru import logger
from pydantic import BaseModel, Field
from sqlmodel import select

if TYPE_CHECKING:
    from ...engine.async_executor import ProgressEvent

from app.db.models import CardType
from app.schemas.response_registry import RESPONSE_MODEL_MAP
from app.services.ai.core.model_builder import build_model_from_json_schema
from app.services.ai.core.llm_service import generate_structured
from ...expressions.evaluator import evaluate_expression
from ...registry import register_node
from ..base import BaseNode


class SequentialStructuredInput(BaseModel):
    """顺序结构化生成输入"""

    items: List[Any] = Field(..., description="数据列表（按顺序处理）")
    llm_config_id: int = Field(..., description="LLM 配置 ID", json_schema_extra={"x-component": "LLMSelect"})
    prompt_template: str = Field(
        ...,
        description="提示词模板，支持 {{content}} / {{item.xxx}} / {{carry.xxx}}",
        json_schema_extra={"x-component": "Textarea"},
    )
    response_model_id: str = Field(..., description="响应模型", json_schema_extra={"x-component": "ResponseModelSelect"})
    temperature: Optional[float] = Field(
        None,
        description="采样温度（可选，默认使用模型配置）",
        ge=0.0,
        le=2.0,
    )
    max_tokens: Optional[int] = Field(
        None,
        description="最大输出 token（可选，默认使用模型配置）",
        ge=1,
    )
    timeout: Optional[float] = Field(
        None,
        description="单次调用超时秒数（可选，默认使用模型配置）",
        gt=0,
    )
    max_retries: int = Field(3, description="最大重试次数", ge=1)
    use_instruction_flow: bool = Field(
        False,
        description="是否使用指令流模式（复杂结构推荐开启，简单结构可关闭以使用原生结构化）",
    )
    overlap_size: int = Field(0, description="重叠窗口大小（可选，默认0）", ge=0)
    initial_carry: Optional[Dict[str, Any]] = Field(None, description="初始承接状态")
    carry_extract_expr: Optional[str] = Field(
        None,
        description="从当前轮结果提取下一轮 carry 的表达式（可选）",
        json_schema_extra={"x-component": "Textarea"},
    )
    fail_soft: bool = Field(False, description="单项失败时是否降级并继续")


class SequentialStructuredOutput(BaseModel):
    """顺序结构化生成输出"""

    results: List[Dict[str, Any]] = Field(..., description="每轮结果（ai_result/meta/carry_in/carry_out）")
    final_carry: Dict[str, Any] = Field(..., description="最终 carry 状态")
    errors: List[Dict[str, Any]] = Field(..., description="错误列表")


@register_node
class SequentialStructuredNode(BaseNode[SequentialStructuredInput, SequentialStructuredOutput]):
    """
    按顺序执行结构化生成并承接 carry 的 AI 节点。
    用法要点：
    - `items` 按顺序逐项处理，天然支持跨项上下文承接。
    - `prompt_template` 支持 `{{content}}`、`{{item.xxx}}`、`{{carry.xxx}}`、`{{overlap_size}}` 占位。
    - 通过 `carry_extract_expr` 从本轮 `ai_result` 提取下一轮 carry（必须返回 dict 或 None）。
    - 可选透传 `temperature/max_tokens/timeout`，细调结构化生成质量与稳定性。
    - 运行中会持续产出 `ProgressEvent`，并把 `partial_results/carry_state` 写入 checkpoint，支持断点恢复。
    """

    node_type = "AI.SequentialStructured"
    category = "ai"
    label = "顺序结构化生成"
    description = "顺序调用结构化生成，支持跨轮 carry 承接与断点恢复"

    input_model = SequentialStructuredInput
    output_model = SequentialStructuredOutput

    async def execute(
        self,
        inputs: SequentialStructuredInput,
    ) -> AsyncIterator[Union["ProgressEvent", SequentialStructuredOutput]]:
        from ...engine.async_executor import ProgressEvent

        items = inputs.items
        if not isinstance(items, list):
            raise ValueError("输入 items 必须是列表")

        if not inputs.prompt_template:
            raise ValueError("提示词模板为空")

        if not items:
            yield SequentialStructuredOutput(
                results=[],
                final_carry=copy.deepcopy(inputs.initial_carry or {}),
                errors=[],
            )
            return

        total = len(items)
        schema = self._get_schema(self.context.session, inputs)
        if not schema:
            raise ValueError(f"无法加载模型 Schema: {inputs.response_model_id}")
        dynamic_output = build_model_from_json_schema(
            f"SequentialStructured_{inputs.response_model_id}",
            schema,
        )

        checkpoint = getattr(self.context, "checkpoint", None) or {}
        results = self._normalize_result_list(checkpoint.get("partial_results", []))
        errors = self._normalize_result_list(checkpoint.get("errors", []))
        processed_indices = self._normalize_index_set(checkpoint.get("processed_indices", []), total)

        carry_state = checkpoint.get("carry_state")
        if not isinstance(carry_state, dict):
            carry_state = copy.deepcopy(inputs.initial_carry or {})

        current_index = checkpoint.get("current_index")
        if not isinstance(current_index, int):
            current_index = len(results)

        current_index = max(current_index, len(results), len(processed_indices))
        current_index = min(current_index, total)

        if current_index > 0:
            logger.info(
                f"[SequentialStructured] 从检查点恢复: 已处理 {current_index}/{total}, "
                f"errors={len(errors)}"
            )

        if current_index >= total:
            yield SequentialStructuredOutput(
                results=results,
                final_carry=carry_state,
                errors=errors,
            )
            return

        for index in range(current_index, total):
            item = items[index]
            carry_in = copy.deepcopy(carry_state)

            try:
                rendered_prompt = self._render_prompt(
                    template=inputs.prompt_template,
                    item=item,
                    carry=carry_in,
                    overlap_size=inputs.overlap_size,
                )

                logger.info(f"[SequentialStructured] Item {index}: 开始 LLM 调用")
                generated = await generate_structured(
                    session=self.context.session,
                    llm_config_id=inputs.llm_config_id,
                    user_prompt=rendered_prompt,
                    output_type=dynamic_output,
                    system_prompt=None,
                    deps="",
                    temperature=inputs.temperature or 0.7,
                    max_tokens=inputs.max_tokens,
                    timeout=inputs.timeout or 150,
                    max_retries=inputs.max_retries,
                    use_instruction_flow=inputs.use_instruction_flow,
                    track_stats=True,
                    return_logs=True,
                )
                ai_result = generated["result"].model_dump(mode="json")
                logger.info(f"[SequentialStructured] Item {index}: ✅ LLM 调用完成")

                carry_out = self._extract_carry(
                    expr=inputs.carry_extract_expr,
                    ai_result=ai_result,
                    item=item,
                    carry=carry_in,
                    index=index,
                    results=results,
                    errors=errors,
                )

                result_item = {
                    "index": index,
                    "ai_result": ai_result,
                    "logs": generated["logs"],
                    "meta": item,
                    "carry_in": carry_in,
                    "carry_out": carry_out,
                }
                results.append(result_item)
                carry_state = carry_out
                processed_indices.add(index)

            except Exception as e:
                logger.error(f"[SequentialStructured] Item {index} 处理失败: {e}")
                error_item = {"index": index, "item": item, "error": str(e)}
                errors.append(error_item)

                if not inputs.fail_soft:
                    raise

                results.append(
                    {
                        "index": index,
                        "error": str(e),
                        "meta": item,
                        "carry_in": carry_in,
                        "carry_out": carry_state,
                    }
                )
                processed_indices.add(index)

            percent = ((index + 1) / total) * 100
            yield ProgressEvent(
                percent=percent,
                message=f"已处理 {index + 1}/{total} 个项目",
                data={
                    "current_index": index + 1,
                    "processed_indices": sorted(processed_indices),
                    "carry_state": carry_state,
                    "partial_results": results,
                    "errors": errors,
                },
            )

        yield SequentialStructuredOutput(
            results=results,
            final_carry=carry_state,
            errors=errors,
        )

    def _render_prompt(
        self,
        template: str,
        item: Any,
        carry: Dict[str, Any],
        overlap_size: int,
    ) -> str:
        content = self._extract_content(item)
        rendered = template.replace("{{content}}", str(content))
        rendered = rendered.replace("{{item}}", self._to_text(item))
        rendered = rendered.replace("{{carry}}", self._to_text(carry))
        rendered = rendered.replace("{{overlap_size}}", str(overlap_size))

        rendered = self._render_prefix_fields(rendered, "item", item)
        rendered = self._render_prefix_fields(rendered, "carry", carry)
        return rendered

    def _render_prefix_fields(self, text: str, prefix: str, value: Any, path: Optional[List[str]] = None) -> str:
        current_path = path or []
        placeholder = "{{" + ".".join([prefix, *current_path]) + "}}"

        if current_path:
            text = text.replace(placeholder, self._to_text(value))

        if isinstance(value, dict):
            for key, child in value.items():
                text = self._render_prefix_fields(text, prefix, child, [*current_path, str(key)])

        return text

    def _extract_content(self, item: Any) -> str:
        if not isinstance(item, dict):
            return str(item)

        content = ""
        path = item.get("path")

        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as file:
                    content = file.read()
            except Exception as e:
                logger.error(f"[SequentialStructured] 读取文件失败: {path}, {e}")
                content = f"[读取失败: {e}]"

        if not content and "content" in item:
            content = self._to_text(item.get("content"))

        return content

    def _extract_carry(
        self,
        expr: Optional[str],
        ai_result: Any,
        item: Any,
        carry: Dict[str, Any],
        index: int,
        results: List[Dict[str, Any]],
        errors: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not expr:
            return copy.deepcopy(carry)

        next_carry = evaluate_expression(
            expr,
            {
                "ai_result": ai_result,
                "item": item,
                "carry": carry,
                "index": index,
                "results": results,
                "errors": errors,
            },
        )

        if next_carry is None:
            return {}

        if not isinstance(next_carry, dict):
            raise ValueError("carry_extract_expr 必须返回 dict 或 None")

        return next_carry

    def _normalize_result_list(self, value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _normalize_index_set(self, value: Any, total: int) -> set[int]:
        if not isinstance(value, list):
            return set()

        normalized: set[int] = set()
        for item in value:
            try:
                index = int(item)
            except Exception:
                continue

            if 0 <= index < total:
                normalized.add(index)

        return normalized

    def _to_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)

        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)

    def _get_schema(self, session, inputs: SequentialStructuredInput) -> Optional[Dict[str, Any]]:
        """根据配置获取 JSON Schema"""

        stmt = select(CardType).where(CardType.name == inputs.response_model_id)
        ct = session.exec(stmt).first()
        if ct and ct.json_schema:
            return ct.json_schema

        builtin_model = RESPONSE_MODEL_MAP.get(inputs.response_model_id)
        if builtin_model is not None:
            return builtin_model.model_json_schema(ref_template="#/$defs/{model}")

        return None
