"""提示词加载节点

从数据库加载预设提示词并渲染模板变量。
"""

from typing import Any, Dict, Optional, Union, AsyncIterator
from pydantic import BaseModel, Field
from loguru import logger
from sqlmodel import select

from ...registry import register_node
from ..base import BaseNode
from app.services.prompt_service import get_prompt, render_prompt
from app.db.models import Prompt


class PromptLoadInput(BaseModel):
    """提示词加载输入"""
    prompt_id: Union[int, str] = Field(
        ...,
        description="提示词 ID 或 名称",
        json_schema_extra={"x-component": "PromptSelect"}
    )
    variables: Optional[Dict[str, Any]] = Field(None, description="模板变量（用于渲染）")


class PromptLoadOutput(BaseModel):
    """提示词加载输出"""
    text: str = Field(..., description="渲染后的提示词文本")


@register_node
class PromptLoadNode(BaseNode[PromptLoadInput, PromptLoadOutput]):
    """提示词加载节点"""
    
    node_type = "Prompt.Load"
    category = "data"
    label = "加载提示词"
    description = "从数据库加载预设提示词模板"
    
    input_model = PromptLoadInput
    output_model = PromptLoadOutput

    async def execute(self, inputs: PromptLoadInput) -> AsyncIterator[PromptLoadOutput]:
        """执行提示词加载"""
        variables = inputs.variables or {}
        
        try:
            # 获取提示词
            prompt_obj = None
            
            # 支持通过 ID 或 Name 查找
            if isinstance(inputs.prompt_id, int):
                prompt_obj = get_prompt(self.context.session, inputs.prompt_id)
            else:
                # 按名称查找
                statement = select(Prompt).where(Prompt.name == inputs.prompt_id)
                results = self.context.session.exec(statement)
                prompt_obj = results.first()
            
            if not prompt_obj:
                raise ValueError(f"未找到提示词: {inputs.prompt_id}")
            
            # 合并全局变量
            template_vars = {
                **self.context.variables,
                **variables,
            }
            
            # 渲染提示词
            rendered_text = render_prompt(prompt_obj.template, template_vars)
            
            logger.info(
                f"[Prompt.Load] 加载提示词成功: prompt={inputs.prompt_id}, "
                f"length={len(rendered_text)}"
            )
            
            yield PromptLoadOutput(text=rendered_text)
            
        except Exception as e:
            logger.error(f"[Prompt.Load] 加载提示词失败: {e}")
            raise
