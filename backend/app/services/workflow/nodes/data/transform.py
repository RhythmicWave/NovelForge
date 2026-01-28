from typing import Any, Dict
from pydantic import Field

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig
from ...expressions import evaluate_expression


class DataTransformConfig(BaseNodeConfig):
    expression: str = Field(..., description="转换表达式")


@register_node
class DataTransformNode(BaseNode):
    node_type = "Data.Transform"
    category = "data"
    label = "数据转换"
    description = "使用表达式转换数据"
    config_model = DataTransformConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [NodePort("input", "any", description="输入数据")],
            "outputs": [NodePort("output", "any", description="输出数据")]
        }

    async def execute(self, inputs: Dict[str, Any], config: DataTransformConfig) -> ExecutionResult:
        """数据转换节点"""
        input_data = inputs.get("input")
        
        try:
            eval_context = {
                "input": input_data,
                **self.context.variables
            }
            
            result = evaluate_expression(config.expression, eval_context)
            
            return ExecutionResult(
                success=True,
                outputs={"output": result}
            )
        
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"表达式求值失败: {str(e)}"
            )
