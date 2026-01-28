from typing import Dict, Any
from app.services.workflow.nodes.base import BaseNode, BaseNodeConfig
from app.services.workflow.registry import register_node
from app.services.workflow.types import NodePort, ExecutionResult

class TriggerProjectConfig(BaseNodeConfig):
    pass

@register_node
class TriggerProjectCreatedNode(BaseNode):
    node_type = "Trigger.ProjectCreated"
    category = "trigger"
    label = "项目创建触发器"
    description = "当新项目创建时触发"
    config_model = TriggerProjectConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [],
            "outputs": [
                NodePort("project_id", "number", description="项目ID"),
                NodePort("project_name", "string", description="项目名称"),
                NodePort("user_id", "number", description="创建者ID"),
                NodePort("created_at", "string", description="创建时间"),
                # 为了兼容默认连线（edges 默认为 output），增加一个 output 端口
                NodePort("output", "number", description="项目ID (兼容)")
            ]
        }

    @classmethod
    def extract_trigger_info(cls, config: Any) -> tuple[str | None, dict | None]:
        if isinstance(config, dict):
            cfg = config
        else:
            cfg = config.dict()
            
        return "__project_created__", cfg.get("filter")

    async def execute(self, inputs: Dict[str, Any], config: TriggerProjectConfig) -> ExecutionResult:
        # Trigger 节点的数据来源于注入的 inputs (run.params)
        data = inputs
        
        # [NEW] 将触发器数据写入全局变量，支持隐式访问 (e.g. {project_id})
        # 这样后续节点即使不连线也能通过 context.variables 获取
        if self.context.variables is not None:
            self.context.variables.update(data)
            # 同时也保留在 trigger 命名空间中，为了兼容性
            self.context.variables["trigger"] = data
        
        return ExecutionResult(
            success=True,
            outputs={
                "project_id": data.get("project_id"),
                "project_name": data.get("name"),
                "user_id": data.get("user_id"),
                "created_at": data.get("created_at"),
                "output": data.get("project_id") # 默认输出项目ID
            }
        )
