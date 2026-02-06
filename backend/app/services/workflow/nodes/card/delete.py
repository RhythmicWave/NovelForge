from typing import Any, Dict, AsyncIterator
from loguru import logger
from pydantic import BaseModel, Field

from ...registry import register_node
from ..base import BaseNode


class CardDeleteInput(BaseModel):
    """删除卡片输入"""
    card: Dict[str, Any] = Field(..., description="要删除的卡片")


class CardDeleteOutput(BaseModel):
    """删除卡片输出"""
    success: bool = Field(..., description="是否成功")


@register_node
class CardDeleteNode(BaseNode[CardDeleteInput, CardDeleteOutput]):
    node_type = "Card.Delete"
    category = "card"
    label = "删除卡片"
    description = "删除指定卡片"
    
    input_model = CardDeleteInput
    output_model = CardDeleteOutput

    async def execute(self, inputs: CardDeleteInput) -> AsyncIterator[CardDeleteOutput]:
        """删除卡片节点"""
        card_id = inputs.card.get("id")
        
        if not card_id:
            raise ValueError("未提供卡片ID")
        
        from ..base import get_card_by_id
        card = get_card_by_id(self.context.session, card_id)
        if not card:
            raise ValueError(f"卡片不存在: {card_id}")
        
        # 删除卡片
        self.context.session.delete(card)
        self.context.session.commit()
        
        logger.info(f"[Card.Delete] 删除卡片: id={card_id}")
        
        yield CardDeleteOutput(success=True)
