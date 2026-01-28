from typing import Any, Dict
from pydantic import Field
from loguru import logger

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig
from ...expressions import evaluate_expression


class DataFilterConfig(BaseNodeConfig):
    condition: str = Field(..., description="过滤条件表达式（item为当前元素）")


@register_node
class DataFilterNode(BaseNode):
    node_type = "Data.Filter"
    category = "data"
    label = "过滤数组"
    description = "根据条件过滤数组元素"
    config_model = DataFilterConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [NodePort("array", "array", description="输入数组")],
            "outputs": [NodePort("output", "array", description="过滤后的数组")]
        }

    async def execute(self, inputs: Dict[str, Any], config: DataFilterConfig) -> ExecutionResult:
        """过滤数组节点"""
        array = inputs.get("array", [])
        
        if not isinstance(array, list):
            return ExecutionResult(
                success=False,
                error="输入不是数组"
            )
        
        try:
            filtered = []
            for item in array:
                eval_context = {
                    "item": item,
                    **self.context.variables
                }
                if evaluate_expression(config.condition, eval_context):
                    filtered.append(item)
            
            logger.info(
                f"[Data.Filter] 过滤数组: {len(array)} -> {len(filtered)}"
            )
            
            return ExecutionResult(
                success=True,
                outputs={"output": filtered}
            )
        
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"过滤失败: {str(e)}"
            )
