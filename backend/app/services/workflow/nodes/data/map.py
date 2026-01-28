from typing import Any, Dict
from pydantic import Field

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig
from ...expressions import evaluate_expression


class DataMapConfig(BaseNodeConfig):
    expression: str = Field(..., description="映射表达式（item为当前元素）")


@register_node
class DataMapNode(BaseNode):
    node_type = "Data.Map"
    category = "data"
    label = "映射数组"
    description = "对数组每个元素应用转换"
    config_model = DataMapConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [NodePort("array", "array", description="输入数组")],
            "outputs": [NodePort("output", "array", description="转换后的数组")]
        }

    async def execute(self, inputs: Dict[str, Any], config: DataMapConfig) -> ExecutionResult:
        """映射数组节点"""
        array = inputs.get("array", [])
        
        if not isinstance(array, list):
            return ExecutionResult(
                success=False,
                error="输入不是数组"
            )
        
        try:
            mapped = []
            for item in array:
                eval_context = {
                    "item": item,
                    **self.context.variables
                }
                result = evaluate_expression(config.expression, eval_context)
                mapped.append(result)
            
            return ExecutionResult(
                success=True,
                outputs={"output": mapped}
            )
        
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"映射失败: {str(e)}"
            )
