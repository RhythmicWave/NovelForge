from typing import Any, Dict, Optional, AsyncIterator
from loguru import logger
from pydantic import BaseModel, Field

from app.db.models import Card
from ...registry import register_node
from ..base import BaseNode, get_card_type_by_name, resolve_card_reference


class CardReadInput(BaseModel):
    """读取卡片输入"""
    target: Optional[Any] = Field("$self", description="卡片引用：数字ID、$self、$parent")
    card_id: Optional[int] = Field(None, description="卡片ID（覆盖target）")
    type_name: Optional[str] = Field(None, description="卡片类型名称（可选）")


class CardReadOutput(BaseModel):
    """读取卡片输出
    
    直接返回卡片字段（扁平结构），便于后续节点访问。
    
    访问示例：
    - card.id: 卡片ID
    - card.title: 卡片标题  
    - card.content: 卡片内容（字典）
    - card.content.get('field_name'): 访问内容字段
    """
    id: int = Field(..., description="卡片ID")
    title: str = Field(..., description="卡片标题")
    content: Dict[str, Any] = Field(..., description="卡片内容")
    card_type_id: int = Field(..., description="卡片类型ID")
    parent_id: Optional[int] = Field(None, description="父卡片ID")


@register_node
class CardReadNode(BaseNode[CardReadInput, CardReadOutput]):
    node_type = "Card.Read"
    category = "card"
    label = "读取卡片"
    description = "读取指定卡片的内容"
    
    input_model = CardReadInput
    output_model = CardReadOutput

    async def execute(self, inputs: CardReadInput) -> AsyncIterator[CardReadOutput]:
        """读取卡片节点"""
        # 优先使用 card_id
        target = inputs.card_id if inputs.card_id is not None else inputs.target
        
        # 解析引用
        card = None
        if isinstance(target, int):
            from ..base import get_card_by_id
            card = get_card_by_id(self.context.session, target)
        else:
            card = resolve_card_reference(
                self.context.session,
                target,
                self.context.variables.get("card_id")
            )
            
            if not card and isinstance(target, str) and target.isdigit():
                from ..base import get_card_by_id
                card = get_card_by_id(self.context.session, int(target))
        
        if not card:
            raise ValueError(f"未找到卡片: {target}")
        
        # 记录受影响的卡片
        touched = self.context.variables.setdefault("touched_card_ids", [])
        if card.id not in touched:
            touched.append(card.id)
        
        # 获取类型信息
        card_type_info = None
        if inputs.type_name:
            card_type = get_card_type_by_name(self.context.session, inputs.type_name)
            if card_type:
                card_type_info = {
                    "id": card_type.id,
                    "name": card_type.name,
                    "schema": card_type.json_schema
                }
        
        logger.info(
            f"[Card.Read] 读取卡片: id={card.id}, title={card.title}"
        )
        
        yield CardReadOutput(
            id=card.id,
            title=card.title,
            content=card.content,
            card_type_id=card.card_type_id,
            parent_id=card.parent_id
        )
