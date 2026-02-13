"""项目创建触发器节点"""
from typing import Optional
from pydantic import BaseModel, Field

from ..base import BaseNode
from ...registry import register_node


class TriggerProjectCreatedInput(BaseModel):
    """项目创建触发器输入"""
    template: Optional[str] = Field(
        None,
        description="模板名称（可选）。只触发指定模板的项目创建，如 'snowflake'。留空则匹配所有模板"
    )


class TriggerProjectCreatedOutput(BaseModel):
    """项目创建触发器输出"""
    project_id: int = Field(..., description="项目ID")
    template: Optional[str] = Field(None, description="模板名称（如 'snowflake'）")


@register_node
class TriggerProjectCreatedNode(BaseNode):
    """项目创建触发器
    
    当新项目创建时触发工作流。
    
    输出字段：
        - project_id: 项目ID
        - template: 模板名称（如果指定了模板）
    
    过滤条件：
        - template: 只触发指定模板的项目创建（可选）
    
    示例:
        # 监听所有项目创建
        trigger = Trigger.ProjectCreated()
        
        # 只监听雪花创作法模板
        trigger = Trigger.ProjectCreated(template="snowflake")
        
        # 使用触发器输出
        card = Card.Create(
            project_id=trigger.project_id,
            card_type="核心蓝图",
            title="核心蓝图"
        )
    """
    
    node_type = "Trigger.ProjectCreated"
    category = "trigger"
    label = "项目创建触发器"
    description = "当新项目创建时触发"
    
    input_model = TriggerProjectCreatedInput
    output_model = TriggerProjectCreatedOutput
    
    async def execute(self, inputs: TriggerProjectCreatedInput):
        """从上下文中读取触发器数据并输出
        
        触发器数据在工作流启动时通过 initial_context["__trigger_data__"] 注入，
        可以通过 self.context.variables 访问。
        """
        # 从上下文的 variables 中获取触发器数据
        trigger_data = self.context.variables.get("__trigger_data__", {})
        
        yield TriggerProjectCreatedOutput(
            project_id=trigger_data.get("project_id"),
            template=trigger_data.get("template")
        )
