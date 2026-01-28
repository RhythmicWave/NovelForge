from typing import Any, Dict
from pydantic import Field
from loguru import logger

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig
from ...expressions import evaluate_expression


class LogicConditionConfig(BaseNodeConfig):
    condition: str = Field(..., description="条件表达式")


@register_node
class LogicConditionNode(BaseNode):
    node_type = "Logic.Condition"
    category = "logic"
    label = "条件分支"
    description = "根据条件选择执行路径"
    config_model = LogicConditionConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [NodePort("input", "any", description="输入数据")],
            "outputs": [
                NodePort("true", "any", description="条件为真时输出"),
                NodePort("false", "any", description="条件为假时输出")
            ]
        }

    async def execute(self, inputs: Dict[str, Any], config: LogicConditionConfig) -> ExecutionResult:
        """条件节点 - 根据表达式判断"""
        input_data = inputs.get("input")
        
        try:
            # 准备求值环境
            eval_context = {
                "input": input_data,
                **self.context.variables
            }
            
            # 使用安全的表达式求值器
            result = evaluate_expression(config.condition, eval_context)
            is_true = bool(result)
            
            logger.info(
                f"[Condition] 条件求值: {config.condition} = {is_true}"
            )
            
            # 使用 activated_ports 显式声明激活的分支
            # 这样执行器可以准确知道哪个分支应该执行
            return ExecutionResult(
                success=True,
                outputs={
                    "true": input_data,      # 数据可以是任意值，包括 None
                    "false": input_data,     # 数据可以是任意值，包括 None
                    "condition_result": is_true
                },
                activated_ports=["true"] if is_true else ["false"]  # 显式声明激活的端口
            )
        
        except Exception as e:
            logger.error(f"[Condition] 条件求值失败: {e}")
            return ExecutionResult(
                success=False,
                error=f"条件求值失败: {str(e)}"
            )
