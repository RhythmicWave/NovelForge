"""文本节点

提供静态文本输出，用于手动输入提示词或其他文本内容。
"""

from typing import Any, Dict
from pydantic import Field
from loguru import logger

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class TextConfig(BaseNodeConfig):
    """文本配置"""
    
    content: str = Field(
        "",
        description="文本内容",
        json_schema_extra={"x-component": "Textarea"}
    )


@register_node
class TextNode(BaseNode):
    """文本节点"""
    
    node_type = "Data.Text"
    category = "data"
    label = "文本"
    description = "输出静态文本内容"
    config_model = TextConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [],
            "outputs": [
                NodePort("text", "string", description="文本内容"),
            ]
        }

    async def execute(
        self,
        inputs: Dict[str, Any],
        config: TextConfig
    ) -> ExecutionResult:
        """执行文本输出"""
        
        logger.info(f"[Data.Text] 输出文本: length={len(config.content)}")
        
        return ExecutionResult(
            success=True,
            outputs={"text": config.content}
        )
