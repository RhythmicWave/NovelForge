from typing import Any, Dict, Optional
from loguru import logger
from pydantic import Field
from sqlmodel import select

from app.db.models import Card
from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig, get_card_type_by_name


class CardQueryConfig(BaseNodeConfig):
    card_type: Optional[str] = Field(None, description="卡片类型名称（可选）")
    parent_id: Optional[int] = Field(None, description="父卡片ID（可选）")
    project_id: Optional[int] = Field(None, description="项目ID（可选）")
    limit: int = Field(100, description="最大返回数量")


@register_node
class CardQueryNode(BaseNode):
    node_type = "Card.Query"
    category = "card"
    label = "查询卡片"
    description = "根据条件查询卡片列表"
    config_model = CardQueryConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("parent_id", "number", required=False, description="父卡片ID（覆盖配置）"),
                NodePort("project_id", "number", required=False, description="项目ID（覆盖配置）")
            ],
            "outputs": [NodePort("cards", "card-list", description="卡片列表")]
        }

    async def execute(self, inputs: Dict[str, Any], config: CardQueryConfig) -> ExecutionResult:
        """查询卡片节点"""
        # 构建查询
        stmt = select(Card)
        
        # 添加过滤条件
        if config.card_type:
            card_type = get_card_type_by_name(self.context.session, config.card_type)
            if card_type:
                stmt = stmt.where(Card.card_type_id == card_type.id)
        
            if card_type:
                stmt = stmt.where(Card.card_type_id == card_type.id)
        
        # 1. Parent ID
        pid = inputs.get("parent_id") if inputs.get("parent_id") is not None else config.parent_id
        if pid is not None:
            stmt = stmt.where(Card.parent_id == pid)
        
        # 2. Project ID
        proj_id = inputs.get("project_id") or config.project_id
        if proj_id:
            stmt = stmt.where(Card.project_id == proj_id)
        else:
            # 从触发数据获取项目ID
            trigger_project_id = self.context.variables.get("project_id")
            if not trigger_project_id:
                trigger = self.context.variables.get("trigger", {})
                trigger_project_id = trigger.get("project_id")
            if trigger_project_id:
                stmt = stmt.where(Card.project_id == trigger_project_id)
        
        # 限制数量
        stmt = stmt.limit(config.limit)
        
        # 执行查询
        cards = list(self.context.session.exec(stmt).all())
        
        logger.info(
            f"[Card.Query] 查询卡片: type={config.card_type}, "
            f"parent_id={config.parent_id}, 结果数={len(cards)}"
        )
        
        return ExecutionResult(
            success=True,
            outputs={
                "cards": [
                    {
                        "id": card.id,
                        "title": card.title,
                        "content": card.content,
                        "card_type_id": card.card_type_id,
                        "parent_id": card.parent_id
                    }
                    for card in cards
                ]
            }
        )
