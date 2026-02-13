from typing import Any, Dict, List, Optional, AsyncIterator
from loguru import logger
from pydantic import BaseModel, Field
from sqlmodel import select

from app.db.models import Card
from ...registry import register_node
from ..base import BaseNode, get_card_type_by_name


class CardQueryInput(BaseModel):
    """查询卡片输入"""
    card_type: Optional[str] = Field(None, description="卡片类型名称（可选）")
    parent_id: Optional[int] = Field(None, description="父卡片ID（可选）")
    project_id: Optional[int] = Field(None, description="项目ID（可选）")
    limit: int = Field(100, description="最大返回数量")


class CardQueryOutput(BaseModel):
    """查询卡片输出"""
    cards: List[Dict[str, Any]] = Field(..., description="卡片列表")


@register_node
class CardQueryNode(BaseNode[CardQueryInput, CardQueryOutput]):
    node_type = "Card.Query"
    category = "card"
    label = "查询卡片"
    description = "根据条件查询卡片列表"
    
    input_model = CardQueryInput
    output_model = CardQueryOutput

    async def execute(self, inputs: CardQueryInput) -> AsyncIterator[CardQueryOutput]:
        """查询卡片节点"""
        # 构建查询
        stmt = select(Card)
        
        # 添加过滤条件
        if inputs.card_type:
            card_type = get_card_type_by_name(self.context.session, inputs.card_type)
            if card_type:
                stmt = stmt.where(Card.card_type_id == card_type.id)
        
        # Parent ID
        if inputs.parent_id is not None:
            stmt = stmt.where(Card.parent_id == inputs.parent_id)
        
        # Project ID（如果提供则过滤，否则不过滤）
        if inputs.project_id:
            stmt = stmt.where(Card.project_id == inputs.project_id)
        
        # 限制数量
        stmt = stmt.limit(inputs.limit)
        
        # 执行查询
        cards = list(self.context.session.exec(stmt).all())
        
        logger.info(
            f"[Card.Query] 查询卡片: type={inputs.card_type}, "
            f"parent_id={inputs.parent_id}, 结果数={len(cards)}"
        )
        
        yield CardQueryOutput(
            cards=[
                {
                    "id": card.id,
                    "title": card.title,
                    "content": card.content,
                    "card_type_id": card.card_type_id,
                    "parent_id": card.parent_id
                }
                for card in cards
            ]
        )
