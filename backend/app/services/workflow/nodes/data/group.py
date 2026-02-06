from typing import Any, Dict, List
from pydantic import Field

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class DataGroupConfig(BaseNodeConfig):
    group_by: str = Field(..., description="分组字段 (支持 path 如 item.volume)")


@register_node
class DataGroupNode(BaseNode):
    node_type = "Data.Group"
    category = "data"
    label = "分组数组"
    description = "将数组按照指定字段分组为字典"
    config_model = DataGroupConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [NodePort("array", "list", description="输入数组")],
            "outputs": [
                NodePort("grouped", "object", description="分组字典 {key: [items]}"),
                NodePort("keys", "list", description="所有分组键列表")
            ]
        }

    async def execute(self, inputs: Dict[str, Any], config: DataGroupConfig) -> ExecutionResult:
        array = inputs.get("array", [])
        if not isinstance(array, list):
            return ExecutionResult(success=False, error="输入必须是列表")

        # 支持点号路径访问
        def get_value(obj, path):
            parts = path.split('.')
            current = obj
            
            # 支持 item.field 或 field
            if parts[0] == 'item':
                parts = parts[1:]
                
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                elif hasattr(current, part):
                    current = getattr(current, part)
                else:
                    return None
                if current is None:
                     return None
            return current

        grouped = {}
        keys = []
        
        for item in array:
            key = get_value(item, config.group_by)
            # 转字符串作为key
            key_str = str(key) if key is not None else "uncategorized"
            
            if key_str not in grouped:
                grouped[key_str] = []
                keys.append(key_str) # 保持出现顺序
            
            grouped[key_str].append(item)
            
        return ExecutionResult(
            success=True,
            outputs={
                "grouped": grouped,
                "keys": keys
            }
        )
