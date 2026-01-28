from typing import Any, Dict, Optional
from pydantic import Field

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class LogicGetVariableConfig(BaseNodeConfig):
    variable_name: str = Field(..., description="变量名")
    default_value: Optional[Any] = Field(None, description="默认值（变量不存在时）")


@register_node
class LogicGetVariableNode(BaseNode):
    node_type = "Logic.GetVariable"
    category = "logic"
    label = "获取变量"
    description = "获取全局变量"
    config_model = LogicGetVariableConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [],
            "outputs": [NodePort("value", "any", description="变量值")]
        }

    async def execute(self, inputs: Dict[str, Any], config: LogicGetVariableConfig) -> ExecutionResult:
        """获取变量节点"""
        value = self.context.get_variable(config.variable_name, config.default_value)
        
        return ExecutionResult(
            success=True,
            outputs={"value": value}
        )
