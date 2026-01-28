from typing import Any, Dict

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class LogicStartConfig(BaseNodeConfig):
    pass


@register_node
class LogicStartNode(BaseNode):
    node_type = "Logic.Start"
    category = "logic"
    label = "开始"
    description = "工作流起始节点"
    config_model = LogicStartConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [],
            "outputs": [NodePort("output", "any", description="触发数据")]
        }

    async def execute(self, inputs: Dict[str, Any], config: LogicStartConfig) -> ExecutionResult:
        """开始节点 - 输出触发数据"""
        trigger_data = self.context.variables.get("trigger", {})
        
        return ExecutionResult(
            success=True,
            outputs={"output": trigger_data}
        )
