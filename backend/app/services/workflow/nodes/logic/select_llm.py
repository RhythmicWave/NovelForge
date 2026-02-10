from typing import Any, AsyncIterator, Dict

from loguru import logger
from pydantic import BaseModel, Field

from app.db.models import LLMConfig
from ...registry import register_node
from ..base import BaseNode


class SelectLLMInput(BaseModel):
    """选择 LLM 配置输入"""

    llm_config_id: int = Field(
        ...,
        description="LLM 配置 ID",
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
    description = "选择并输出一个 LLM 配置"

    input_model = SelectLLMInput
    output_model = SelectLLMOutput

    async def execute(self, inputs: SelectLLMInput) -> AsyncIterator[SelectLLMOutput]:
        config = self.context.session.get(LLMConfig, inputs.llm_config_id)
        if not config:
            raise ValueError(f"LLM配置不存在: {inputs.llm_config_id}")

        logger.info(
            f"[SelectLLM] 选择模型: {config.display_name or config.model_name} "
            f"(id={inputs.llm_config_id})"
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

