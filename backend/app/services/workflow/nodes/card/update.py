"""卡片更新节点"""

from typing import Any, Dict, Optional, AsyncIterator
from pydantic import BaseModel, Field

from app.services.workflow.nodes.base import BaseNode
from app.services.workflow.registry import register_node


class CardUpdateInput(BaseModel):
    """卡片更新输入"""
    card_id: Optional[int] = Field(None, description="卡片ID（可选，可从上下文获取）")
    content_merge: Dict[str, Any] = Field(
        default_factory=dict,
        description="要合并的内容（深度合并到现有内容）"
    )
    title: Optional[str] = Field(
        None,
        description="新标题（可选）"
    )


class CardUpdateOutput(BaseModel):
    """卡片更新输出"""
    card_id: int = Field(..., description="更新后的卡片ID")
    success: bool = Field(True, description="是否更新成功")


@register_node
class CardUpdateNode(BaseNode):
    """卡片更新节点
    
    更新现有卡片的内容或标题。
    支持深度合并内容，不会覆盖未指定的字段。
    
    示例：
    1. 清空列表字段：content_merge={"items": []}
    2. 更新嵌套字段：content_merge={"world_view": {"social_system": {"major_power_camps": []}}}
    3. 更新标题：title="新标题"

    严格约束（给工作流编写 Agent）：
    - `content_merge` 必须是可静态校验的字面量 dict。
    - 禁止把整个 `content_merge` 写成 `${...}`、`$expr.result` 或字符串拼接结果。
    - 更新字段必须符合目标卡片 schema，禁止写入 schema 不存在字段。

    建议先确定目标卡片类型 schema，再构造 `content_merge`。
    """
    
    node_type = "Card.Update"
    category = "card"
    label = "更新卡片"
    description = "更新现有卡片的内容或标题"
    
    input_model = CardUpdateInput
    output_model = CardUpdateOutput
    
    async def execute(self, input_data: CardUpdateInput) -> AsyncIterator[CardUpdateOutput]:
        """执行卡片更新"""
        from sqlmodel import select
        from app.db.models import Card
        
        # 确定卡片ID
        card_id = input_data.card_id
        if not card_id:
            raise ValueError("必须提供 card_id")
        
        # 获取卡片
        card = self.context.session.get(Card, card_id)
        if not card:
            raise ValueError(f"卡片不存在: card_id={card_id}")
        
        # 更新标题
        if input_data.title:
            card.title = input_data.title
        
        # 深度合并内容
        if input_data.content_merge:
            card.content = self._deep_merge(card.content or {}, input_data.content_merge)
        
        # 保存
        self.context.session.add(card)
        self.context.session.commit()
        self.context.session.refresh(card)
        
        yield CardUpdateOutput(
            card_id=card.id,
            success=True
        )
    
    def _deep_merge(self, base: Dict, update: Dict) -> Dict:
        """深度合并字典
        
        Args:
            base: 基础字典
            update: 更新字典
            
        Returns:
            合并后的字典
        """
        result = base.copy()
        
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # 递归合并嵌套字典
                result[key] = self._deep_merge(result[key], value)
            else:
                # 直接覆盖
                result[key] = value
        
        return result
