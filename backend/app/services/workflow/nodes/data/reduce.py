from typing import Any, Dict, Optional
from pydantic import Field

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig
from ...expressions import evaluate_expression


class DataReduceConfig(BaseNodeConfig):
    expression: str = Field(..., description="归约表达式（accumulator和item）")
    initial_value: Optional[Any] = Field(None, description="初始值")


@register_node
class DataReduceNode(BaseNode):
    node_type = "Data.Reduce"
    category = "data"
    label = "归约数组"
    description = "将数组归约为单个值"
    config_model = DataReduceConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [NodePort("array", "array", description="输入数组")],
            "outputs": [NodePort("output", "any", description="归约结果")]
        }

    async def execute(self, inputs: Dict[str, Any], config: DataReduceConfig) -> ExecutionResult:
        """归约数组节点"""
        array = inputs.get("array", [])
        
        if not isinstance(array, list):
            return ExecutionResult(
                success=False,
                error="输入不是数组"
            )
        
        try:
            accumulator = config.initial_value
            for item in array:
                eval_context = {
                    "accumulator": accumulator,
                    "item": item,
                    **self.context.variables
                }
                accumulator = evaluate_expression(config.expression, eval_context)
            
            return ExecutionResult(
                success=True,
                outputs={"output": accumulator}
            )
        
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"归约失败: {str(e)}"
            )
