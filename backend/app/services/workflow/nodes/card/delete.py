from typing import Any, Dict
from loguru import logger

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class CardDeleteConfig(BaseNodeConfig):
    pass  # 删除节点可能不需要额外配置，或者以后可以添加 soft_delete 选项


@register_node
class CardDeleteNode(BaseNode):
    node_type = "Card.Delete"
    category = "card"
    label = "删除卡片"
    description = "删除指定卡片"
    config_model = CardDeleteConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [NodePort("card", "card", description="要删除的卡片")],
            "outputs": [NodePort("success", "boolean", description="是否成功")]
        }

    async def execute(self, inputs: Dict[str, Any], config: CardDeleteConfig) -> ExecutionResult:
        """删除卡片节点"""
        card_data = inputs.get("card", {})
        card_id = card_data.get("id")
        
        if not card_id:
            return ExecutionResult(
                success=False,
                error="未提供卡片ID"
            )
        
        card = self.get_card_by_id(card_id)
        if not card:
            return ExecutionResult(
                success=False,
                error=f"卡片不存在: {card_id}"
            )
        
        # 保存卡片信息用于补偿
        from ...engine.state_manager import StateManager
        state_manager = StateManager(self.context.session)
        state_manager.add_compensation_log(
            run_id=self.context.run_id,
            operation="card.deleted",
            card_id=card.id,
            card_data={
                "title": card.title,
                "content": card.content,
                "card_type_id": card.card_type_id,
                "parent_id": card.parent_id,
                "project_id": card.project_id
            }
        )
        
        # 删除卡片
        self.context.session.delete(card)
        self.context.session.commit()
        
        logger.info(f"[Card.Delete] 删除卡片: id={card_id}")
        
        return ExecutionResult(
            success=True,
            outputs={"success": True}
        )
