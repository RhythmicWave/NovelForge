from typing import Any, AsyncIterator, Dict

from loguru import logger
from pydantic import BaseModel, Field
from sqlmodel import select

from app.db.models import LLMConfig
from ...registry import register_node
from ..base import BaseNode


class SelectLLMInput(BaseModel):
    """选择 LLM 配置输入"""

    llm_config_id: int | None = Field(
        default=None,
        description="LLM 配置 ID",
        json_schema_extra={"x-component": "LLMSelect"},
    )
    llm_name: str | None = Field(
        default=None,
        description="模型显示名或 model_name（当 llm_config_id 为空时按名称解析，名称和ID提供一个即可）",
        json_schema_extra={"x-component": "LLMSelect"},
    )


class SelectLLMOutput(BaseModel):
    """选择 LLM 配置输出"""

    llm_config_id: int = Field(..., description="LLM 配置 ID")
    llm_config: Dict[str, Any] = Field(..., description="LLM 配置对象")


@register_node
class SelectLLMNode(BaseNode[SelectLLMInput, SelectLLMOutput]):
    node_type = "Logic.SelectLLM"
    category = "logic"
    label = "选择模型"
    description = "选择并输出一个 LLM 配置，可以根据名字、ID来获取具体的LLM配置，包括LLM ID"

    input_model = SelectLLMInput
    output_model = SelectLLMOutput

    async def execute(self, inputs: SelectLLMInput) -> AsyncIterator[SelectLLMOutput]:
        session = self.context.session

        config = None
        if inputs.llm_config_id is not None:
            config = session.get(LLMConfig, inputs.llm_config_id)

        if config is None and inputs.llm_name:
            exact_stmt = select(LLMConfig).where(
                (LLMConfig.display_name == inputs.llm_name)
                | (LLMConfig.model_name == inputs.llm_name)
            )
            exact = session.exec(exact_stmt).all()
            if len(exact) == 1:
                config = exact[0]
            elif len(exact) > 1:
                raise ValueError(f"模型名匹配到多个候选: {inputs.llm_name}")
            else:
                all_rows = session.exec(select(LLMConfig)).all()
                lowered = inputs.llm_name.lower()
                matches = [
                    item
                    for item in all_rows
                    if lowered in (item.display_name or "").lower()
                    or lowered in (item.model_name or "").lower()
                ]
                if len(matches) == 1:
                    config = matches[0]
                elif len(matches) > 1:
                    raise ValueError(f"模型名匹配到多个候选: {inputs.llm_name}")

        if not config:
            raise ValueError(
                f"LLM 配置不存在: id={inputs.llm_config_id}, name={inputs.llm_name}"
            )

        logger.info(
            f"[SelectLLM] 选择模型: {config.display_name or config.model_name} "
            f"(id={config.id})"
        )

        yield SelectLLMOutput(
            llm_config_id=config.id,
            llm_config={
                "id": config.id,
                "display_name": config.display_name,
                "model_name": config.model_name,
                "provider": config.provider,
                "api_base": config.api_base,
            },
        )
