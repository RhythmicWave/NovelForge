"""提示词加载节点

从数据库加载预设提示词并渲染模板变量。
"""

from typing import Any, Dict, Optional, Union
from pydantic import Field
from loguru import logger
from sqlmodel import select

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig
from app.services.prompt_service import get_prompt, render_prompt
from app.db.models import Prompt


class PromptLoadConfig(BaseNodeConfig):
    """提示词加载配置"""
    
    prompt_id: Union[int, str] = Field(
        ...,
        description="提示词 ID 或 名称",
        json_schema_extra={"x-component": "PromptSelect"}
    )


@register_node
class PromptLoadNode(BaseNode):
    """提示词加载节点"""
    
    node_type = "Prompt.Load"
    category = "data"
    label = "加载提示词"
    description = "从数据库加载预设提示词模板"
    config_model = PromptLoadConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("variables", "object", required=False, description="模板变量（用于渲染）"),
            ],
            "outputs": [
                NodePort("text", "string", description="渲染后的提示词文本"),
            ]
        }

    async def execute(
        self,
        inputs: Dict[str, Any],
        config: PromptLoadConfig
    ) -> ExecutionResult:
        """执行提示词加载"""
        
        variables = inputs.get("variables", {})
        
        try:
            # 获取提示词
            prompt_obj = None
            
            # 支持通过 ID 或 Name 查找
            if isinstance(config.prompt_id, int):
                prompt_obj = get_prompt(self.context.session, config.prompt_id)
            else:
                # 按名称查找
                statement = select(Prompt).where(Prompt.name == config.prompt_id)
                results = self.context.session.exec(statement)
                prompt_obj = results.first()
            
            if not prompt_obj:
                return ExecutionResult(
                    success=False,
                    error=f"未找到提示词: {config.prompt_id}"
                )
            
            # 合并全局变量
            template_vars = {
                **self.context.variables,
                **variables,
            }
            
            # 渲染提示词
            rendered_text = render_prompt(prompt_obj.template, template_vars)
            
            logger.info(
                f"[Prompt.Load] 加载提示词成功: promt={config.prompt_id}, "
                f"length={len(rendered_text)}"
            )
            
            return ExecutionResult(
                success=True,
                outputs={"text": rendered_text}
            )
            
        except Exception as e:
            logger.error(f"[Prompt.Load] 加载提示词失败: {e}")
            return ExecutionResult(
                success=False,
                error=f"加载提示词失败: {str(e)}"
            )
