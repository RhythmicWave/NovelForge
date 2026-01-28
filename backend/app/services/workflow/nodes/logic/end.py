from typing import Any, Dict

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class LogicEndConfig(BaseNodeConfig):
    pass


@register_node
class LogicEndNode(BaseNode):
    node_type = "Logic.End"
    category = "logic"
    label = "结束"
    description = "工作流结束节点"
    config_model = LogicEndConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [NodePort("input", "any", description="最终输出")],
            "outputs": []
        }

    async def execute(self, inputs: Dict[str, Any], config: LogicEndConfig) -> ExecutionResult:
        """结束节点 - 标记工作流完成"""
        final_output = inputs.get("input")
        
        return ExecutionResult(
            success=True,
            outputs={"result": final_output}
        )
