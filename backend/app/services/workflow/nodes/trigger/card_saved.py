"""卡片保存触发器节点"""
from typing import Optional
from pydantic import BaseModel, Field

from ..base import BaseNode
from ...registry import register_node


class TriggerCardSavedInput(BaseModel):
    """卡片保存触发器输入"""
    card_type: Optional[str] = Field(
        None,
        description="卡片类型名称（可选）。只触发指定类型的卡片保存，如 '核心蓝图'。留空则匹配所有类型"
    )
    on_create: bool = Field(
        True,
        description="是否在卡片创建时触发"
    )
    on_update: bool = Field(
        True,
        description="是否在卡片更新时触发"
    )


class TriggerCardSavedOutput(BaseModel):
    """卡片保存触发器输出"""
    card_id: int = Field(..., description="卡片ID")
    project_id: int = Field(..., description="项目ID")
    card_type: Optional[str] = Field(None, description="卡片类型名称")
    is_created: bool = Field(..., description="是否是新创建的卡片（true=创建，false=更新）")


@register_node
class TriggerCardSavedNode(BaseNode):
    """卡片保存触发器
    
    当卡片保存时触发工作流（包括创建和更新）。
    
    输出字段：
        - card_id: 卡片ID
        - project_id: 项目ID
        - card_type: 卡片类型名称
        - is_created: 是否是新创建的卡片
    
    过滤条件：
        - card_type: 只触发指定类型的卡片（可选）
        - on_create: 是否在创建时触发（默认 true）
        - on_update: 是否在更新时触发（默认 true）
    
    示例:
        # 监听所有卡片保存
        trigger = Trigger.CardSaved()
        
        # 只监听核心蓝图卡片的更新
        trigger = Trigger.CardSaved(
            card_type="核心蓝图",
            on_create=false,
            on_update=true
        )
        
        # 使用触发器输出
        card = Card.Get(card_id=trigger.card_id)
        
        # 提取关系
        relations = AI.ExtractRelations(
            card_id=trigger.card_id,
            project_id=trigger.project_id
        )
    """
    
    node_type = "Trigger.CardSaved"
    category = "trigger"
    label = "卡片保存触发器"
    description = "当卡片保存时触发"
    
    input_model = TriggerCardSavedInput
    output_model = TriggerCardSavedOutput
    
    async def execute(self, inputs: TriggerCardSavedInput):
        """从上下文中读取触发器数据并输出
        
        触发器数据在工作流启动时通过 initial_context["__trigger_data__"] 注入，
        可以通过 self.context.variables 访问。
        """
        # 从上下文的 variables 中获取触发器数据
        trigger_data = self.context.variables.get("__trigger_data__", {})

        card_type = trigger_data.get("card_type")
        if card_type is None:
            card_type = inputs.card_type
        
        yield TriggerCardSavedOutput(
            card_id=trigger_data.get("card_id"),
            project_id=trigger_data.get("project_id"),
            card_type=card_type,
            is_created=trigger_data.get("is_created", False)
        )
