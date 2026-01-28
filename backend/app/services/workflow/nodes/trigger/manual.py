from typing import Dict, Any, List, Optional
from app.services.workflow.nodes.base import BaseNode, BaseNodeConfig
from app.services.workflow.registry import register_node
from app.services.workflow.types import NodePort, ExecutionResult

class TriggerManualConfig(BaseNodeConfig):
    # 定义需要的输入参数，可以是简单的列表，用于前端生成表单
    # 暂简化为：参数名列表
    # 未来可以是完整的 JSON Schema
    parameters: List[str] = [] 

@register_node
class TriggerManualNode(BaseNode):
    node_type = "Trigger.Manual"
    category = "trigger"
    label = "手动触发器"
    description = "用于手动运行工作流，可定义输入参数"
    config_model = TriggerManualConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [],
            "outputs": [
                NodePort("params", "object", description="用户输入的参数集合"),
                NodePort("user_id", "string", description="触发用户ID"),
                NodePort("output", "object", description="参数集合 (兼容)")
            ]
        }

    async def execute(self, inputs: Dict[str, Any], config: TriggerManualConfig) -> ExecutionResult:
        # 手动运行时，参数会通过 inputs 传入
        data = inputs
        
        # 写入全局变量，方便后续节点通过 {param_name} 引用
        if self.context.variables is not None:
            self.context.variables.update(data)
            
        return ExecutionResult(
            success=True,
            outputs={
                "params": data,
                "user_id": str(data.get("user_id", "unknown")),
                "output": data # 兼容性输出
            }
        )
