from typing import Any, Dict, Optional, AsyncIterator
from loguru import logger
from pydantic import BaseModel, Field

from app.db.models import Card
from ...registry import register_node
from ..base import BaseNode, get_card_type_by_name


class CardCreateInput(BaseModel):
    """创建卡片输入"""
    project_id: int = Field(..., description="项目ID（必须显式传递）")
    card_type: str = Field(..., description="卡片类型名称")
    title: str = Field(..., description="卡片标题")
    content: Dict[str, Any] = Field(default_factory=dict, description="卡片内容")
    parent: Optional[Dict[str, Any]] = Field(None, description="父卡片")


class CardCreateOutput(BaseModel):
    """创建卡片输出
    
    直接返回卡片字段（扁平结构），便于后续节点访问。
    """
    id: int = Field(..., description="卡片ID")
    title: str = Field(..., description="卡片标题")
    content: Dict[str, Any] = Field(..., description="卡片内容")
    card_type_id: int = Field(..., description="卡片类型ID")
    parent_id: Optional[int] = Field(None, description="父卡片ID")


@register_node
class CardCreateNode(BaseNode[CardCreateInput, CardCreateOutput]):
    """创建卡片节点。

    严格约束（给工作流编写 Agent）：
    1) `content` 必须是字面量 dict（可静态校验），不要把整个 content 写成字符串、`${...}` 或 `Logic.Expression.result`。
    2) 写入前应先确认目标卡片类型 schema（字段名、必填项、字段类型），禁止臆造字段。
    3) 若需要动态内容，请在字段值层面引用已知输出字段，避免整体对象动态拼装。

    推荐流程：
    - 先查询卡片类型 schema
    - 再按 schema 构造 `content={...}`
    """
    node_type = "Card.Create"
    category = "card"
    label = "创建卡片"
    description = "创建新卡片"
    
    input_model = CardCreateInput
    output_model = CardCreateOutput

    async def execute(self, inputs: CardCreateInput) -> AsyncIterator[CardCreateOutput]:
        """创建卡片节点"""
        # 1. 准备数据
        title = inputs.title
        if not title:
            raise ValueError("未提供卡片标题")

        content = inputs.content or {}
        
        # 检查卡片类型
        card_type = get_card_type_by_name(self.context.session, inputs.card_type)
        if not card_type:
            raise ValueError(f"卡片类型不存在: {inputs.card_type}")
        
        # 使用显式传递的 project_id
        project_id = inputs.project_id
        
        parent_data = inputs.parent or {}
        parent_id = parent_data.get("id")
        
        # 使用 CardService 创建卡片
        from app.services.card_service import CardService
        from app.schemas.card import CardCreate
        
        card_service = CardService(self.context.session)
        
        try:
            card_in = CardCreate(
                title=title,
                content=content,
                card_type_id=card_type.id,
                parent_id=parent_id,
                project_id=project_id
            )
            card = card_service.create(card_in, project_id)
            
        except Exception as e:
            logger.error(f"[Card.Create] 创建失败: {e}")
            raise
        
        # 记录受影响的卡片
        touched = self.context.variables.setdefault("touched_card_ids", [])
        if card.id not in touched:
            touched.append(card.id)
        
        logger.info(
            f"[Card.Create] 创建卡片: id={card.id}, title={card.title}, "
            f"type={inputs.card_type}"
        )
        
        yield CardCreateOutput(
            id=card.id,
            title=card.title,
            content=card.content,
            card_type_id=card.card_type_id,
            parent_id=card.parent_id
        )
