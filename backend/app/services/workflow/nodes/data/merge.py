from typing import Any, Dict

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class DataMergeConfig(BaseNodeConfig):
    pass


@register_node
class DataMergeNode(BaseNode):
    node_type = "Data.Merge"
    category = "data"
    label = "合并对象"
    description = "合并多个对象"
    config_model = DataMergeConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("object1", "object", description="对象1"),
                NodePort("object2", "object", description="对象2")
            ],
            "outputs": [NodePort("output", "object", description="合并后的对象")]
        }

    async def execute(self, inputs: Dict[str, Any], config: DataMergeConfig) -> ExecutionResult:
        """合并对象节点"""
        obj1 = inputs.get("object1", {})
        obj2 = inputs.get("object2", {})
        
        if not isinstance(obj1, dict):
            obj1 = {}
        if not isinstance(obj2, dict):
            obj2 = {}
        
        merged = {**obj1, **obj2}
        
        return ExecutionResult(
            success=True,
            outputs={"output": merged}
        )
