from typing import Any, Dict, Optional
from loguru import logger
from pydantic import Field

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class CardUpdateConfig(BaseNodeConfig):
    content_merge: Optional[Dict[str, Any]] = Field(None, description="要合并的内容（浅合并）")
    title: Optional[str] = Field(None, description="新标题（可选）")


@register_node
class CardUpdateNode(BaseNode):
    node_type = "Card.Update"
    category = "card"
    label = "更新卡片"
    description = "更新卡片内容"
    config_model = CardUpdateConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("card", "card", description="要更新的卡片"),
                NodePort("title", "string", required=False, description="新标题"),
                NodePort("content", "object", required=False, description="要合并的内容")
            ],
            "outputs": [NodePort("card", "card", description="更新后的卡片")]
        }

    async def execute(self, inputs: Dict[str, Any], config: CardUpdateConfig) -> ExecutionResult:
        """更新卡片节点"""
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
        
        # 更新标题
        input_title = inputs.get("title")
        final_title = input_title if input_title is not None else config.title
        
        if final_title:
            card.title = final_title
        
        # 合并内容
        input_content = inputs.get("content") or {}
        config_content = config.content_merge or {}
        
        # Merge source: inputs > config
        # 如果 inputs 提供 content, 它将合并到 current content 中
        # 如果 config 提供 content_merge, 它也会合并
        # 这里策略是: 先合并 config, 再合并 inputs
        
        if config_content or input_content:
            # 必须进行深拷贝和重新赋值，以确保 SQLAlchemy 检测到变更
            import copy
            new_content = copy.deepcopy(card.content) if isinstance(card.content, dict) else {}
            
            if config_content:
                self._deep_merge(new_content, config_content)
            
            if input_content:
                self._deep_merge(new_content, input_content)
                
            card.content = new_content
        
        # 保存
        self.context.session.add(card)
        self.context.session.commit()
        self.context.session.refresh(card)
        
        # 记录受影响的卡片
        self.context.variables.setdefault("touched_card_ids", set()).add(card.id)
        
        logger.info(
            f"[Card.Update] 更新卡片: id={card.id}, title={card.title}"
        )
        
        return ExecutionResult(
            success=True,
            outputs={
                "card": {
                    "id": card.id,
                    "title": card.title,
                    "content": card.content,
                    "card_type_id": card.card_type_id,
                    "parent_id": card.parent_id
                }
            }
        )

    def _deep_merge(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """递归合并字典"""
        for key, value in source.items():
            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                self._deep_merge(target[key], value)
            else:
                # 对于列表或基本类型，直接覆盖（如果那是你想要的）
                # 注意：如果 value 是空列表 []，也会覆盖 target[key]，这正是清空列表所需的
                target[key] = value
