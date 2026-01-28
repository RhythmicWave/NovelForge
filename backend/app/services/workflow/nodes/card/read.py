from typing import Any, Dict, Optional
from loguru import logger
from pydantic import Field

from app.db.models import Card
from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig, get_card_type_by_name


class CardReadConfig(BaseNodeConfig):
    target: str = Field("$self", description="卡片引用：数字ID、$self、$parent")
    type_name: Optional[str] = Field(None, description="卡片类型名称（可选）")


@register_node
class CardReadNode(BaseNode):
    node_type = "Card.Read"
    category = "card"
    label = "读取卡片"
    description = "读取指定卡片的内容"
    config_model = CardReadConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("card_id", "number", required=False, description="卡片ID（覆盖配置）")
            ],
            "outputs": [
                NodePort("card", "card", description="卡片对象"),
                NodePort("output", "card", description="卡片对象 (兼容)")
            ]
        }

    async def execute(self, inputs: Dict[str, Any], config: CardReadConfig) -> ExecutionResult:
        """读取卡片节点"""
        # 1. 优先从输入获取 ID
        # 1. 优先从输入获取 ID
        input_id = inputs.get("card_id")
        
        # 兼容性：如果 card_id 为空，尝试从 input 获取
        if input_id is None:
            val = inputs.get("input")
            if isinstance(val, int):
                input_id = val
            elif isinstance(val, str) and val.isdigit():
                input_id = int(val)
            elif isinstance(val, dict):
                # 尝试从对象中提取 id (e.g. card object or trigger data)
                input_id = val.get("id") or val.get("card_id")
                if input_id is None and "card" in val:
                     # handle {card: {...}} structure
                     input_id = val["card"].get("id")
        
        target = input_id if input_id is not None else config.target
        
        # 2. 解析引用
        card = None
        if isinstance(target, int):
            card = self.get_card_by_id(target)
        else:
            card = self.resolve_card_reference(target)
            
            if not card and isinstance(target, str) and target.isdigit():
                 card = self.get_card_by_id(int(target))
        
        if not card:
            return ExecutionResult(
                success=False,
                error=f"未找到卡片: {target}"
            )
        
        # 2. 记录受影响的卡片
        self.context.variables.setdefault("touched_card_ids", set()).add(card.id)
        
        # 3. 获取类型信息
        card_type_info = None
        if config.type_name:
            card_type = get_card_type_by_name(self.context.session, config.type_name)
            if card_type:
                card_type_info = {
                    "id": card_type.id,
                    "name": card_type.name,
                    "schema": card_type.json_schema
                }
        
        logger.info(
            f"[Card.Read] 读取卡片: id={card.id}, title={card.title}"
        )
        
        return ExecutionResult(
            success=True,
            outputs={
                "card": {
                    "id": card.id,
                    "title": card.title,
                    "content": card.content,
                    "card_type_id": card.card_type_id,
                    "parent_id": card.parent_id,
                    "type_info": card_type_info
                },
                "output": { # 兼容性输出
                    "id": card.id,
                    "title": card.title,
                    "content": card.content,
                    "card_type_id": card.card_type_id,
                    "parent_id": card.parent_id
                }
            }
        )
