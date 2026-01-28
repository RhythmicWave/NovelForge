from typing import Dict, Any, Optional, List
from enum import Enum
from pydantic import BaseModel, Field
from app.services.workflow.nodes.base import BaseNode, BaseNodeConfig
from app.services.workflow.registry import register_node
from app.services.workflow.types import NodePort, ExecutionResult

class FilterOperator(str, Enum):
    AND = "and"
    OR = "or"

class ConditionOperator(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    LT = "lt"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    EXISTS = "exists"
    CHANGED = "changed"

class TriggerEventType(str, Enum):
    CREATE = "create"
    UPDATE = "update"

class FilterCondition(BaseModel):
    field: str = Field(..., description="字段路径 (例如 content.status)")
    op: ConditionOperator = Field(default=ConditionOperator.EQ, description="操作符", title="操作符")
    value: Any = Field(None, description="目标值 (exists时填true/false)")

class FilterConfig(BaseModel):
    operator: FilterOperator = Field(default=FilterOperator.AND, description="多条件组合逻辑", title="组合逻辑")
    conditions: List[FilterCondition] = Field(default_factory=list, description="条件列表", title="筛选条件")

class TriggerCardAvailableConfig(BaseNodeConfig):
    card_type: Optional[str] = None  # 卡片类型名称，为空则匹配所有
    events: List[TriggerEventType] = Field(
        default_factory=lambda: [TriggerEventType.UPDATE],
        title="触发事件",
        description="选择触发事件类型",
        json_schema_extra={
            "default": ["update"]
        }
    )
    filter_config: Optional[FilterConfig] = Field(default=None, title="高级过滤")
    
@register_node
class TriggerCardSavedNode(BaseNode):
    node_type = "Trigger.CardSaved"
    category = "trigger"
    label = "卡片保存触发器"
    description = "当卡片内容更新或保存时触发，支持自定义过滤条件"
    config_model = TriggerCardAvailableConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [],
            "outputs": [
                NodePort("card_id", "number", description="卡片ID"),
                NodePort("project_id", "number", description="项目ID"),
                NodePort("card_title", "string", description="卡片标题"),
                NodePort("trigger_event", "string", description="触发事件(create/update)"),
                NodePort("output", "object", description="完整事件数据 (兼容)")
            ]
        }

    @classmethod
    def extract_trigger_info(cls, config: Any) -> tuple[str | None, dict | None]:
        if isinstance(config, dict):
            # 原始字典
            cfg = config
        else:
            # Pydantic model
            cfg = config.dict()
            
        return (
            cfg.get("card_type"),
            cfg.get("filter") or cfg.get("filter_config") # 兼容旧字段
        )

    async def execute(self, inputs: Dict[str, Any], config: TriggerCardAvailableConfig) -> ExecutionResult:
        data = inputs
        
        # 兼容性：写入全局变量
        if self.context.variables is not None:
            self.context.variables.update(data)
            self.context.variables["trigger"] = data
            
        return ExecutionResult(
            success=True,
            outputs={
                "card_id": self.context.variables.get("card_id"),
                "project_id": self.context.variables.get("project_id"),
                "card_title": data.get("card", {}).get("title") if isinstance(data.get("card"), dict) else None,
                "trigger_event": "create" if data.get("is_created") else "update",
                "output": data # 兼容性输出：完整事件数据
            }
        )
