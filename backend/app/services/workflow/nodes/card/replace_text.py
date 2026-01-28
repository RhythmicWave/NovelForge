from typing import Any, Dict, Optional
from loguru import logger
from pydantic import Field

from app.services.card_service import CardService
from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class CardReplaceTextConfig(BaseNodeConfig):
    card_id: Optional[int] = Field(None, description="目标卡片ID")
    field_path: Optional[str] = Field(None, description="字段路径 (如 content.overview)")
    old_text: Optional[str] = Field(None, description="要修改的旧文本")
    new_text: Optional[str] = Field(None, description="新文本")


@register_node
class CardReplaceTextNode(BaseNode):
    node_type = "Card.ReplaceFieldText"
    category = "card"
    label = "替换文本"
    description = "替换卡片字段中的指定文本片段（支持模糊匹配）"
    config_model = CardReplaceTextConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("card", "card", required=False, description="目标卡片对象"),
                NodePort("field_path", "string", required=False, description="字段路径"),
                NodePort("old_text", "string", required=False, description="旧文本"),
                NodePort("new_text", "string", required=False, description="新文本"),
            ],
            "outputs": [
                NodePort("card", "card", description="更新后的卡片"),
                NodePort("replaced_count", "integer", description="替换次数"),
                NodePort("success", "boolean", description="是否成功")
            ]
        }

    async def execute(self, inputs: Dict[str, Any], config: CardReplaceTextConfig) -> ExecutionResult:
        """执行文本替换"""
        # 1. 解析参数 (Inputs 优先于 Config)
        card_input = inputs.get("card")
        card_id = None
        
        if card_input and hasattr(card_input, "id"):
            card_id = card_input.id
        elif isinstance(card_input, dict) and "id" in card_input:
            card_id = card_input["id"]
        else:
            card_id = config.card_id

        # 尝试解析引用
        if not card_id and card_input:
             resolved = self.resolve_card_reference(card_input)
             if resolved:
                 card_id = resolved.id
        
        field_path = inputs.get("field_path") or config.field_path
        old_text = inputs.get("old_text") or config.old_text
        new_text = inputs.get("new_text")
        if new_text is None:
            new_text = config.new_text
        if new_text is None:
            new_text = ""

        # 2. 校验参数
        if not card_id:
            return ExecutionResult(success=False, error="未指定目标卡片 (card 或 card_id)")
        if not field_path:
            return ExecutionResult(success=False, error="未指定字段路径 (field_path)")
        if not old_text:
            return ExecutionResult(success=False, error="未指定旧文本 (old_text)")

        # 3. 调用 Service
        try:
            service = CardService(self.context.session)
            result = service.replace_field_text(
                card_id=int(card_id),
                field_path=str(field_path),
                old_text=str(old_text),
                new_text=str(new_text),
                fuzzy_match=True
            )
            
            if not result["success"]:
                 return ExecutionResult(success=False, error=result.get("error"))

            # 4. 更新 Context 并返回
            # 记录受影响卡片
            self.context.variables.setdefault("touched_card_ids", set()).add(card_id)
            
            # 获取最新卡片对象返回
            updated_card = self.get_card_by_id(card_id)
            
            return ExecutionResult(
                success=True,
                outputs={
                    "card": updated_card,
                    "replaced_count": result.get("replaced_count", 0),
                    "success": True
                }
            )

        except Exception as e:
            logger.error(f"[Card.ReplaceFieldText] 执行失败: {e}", exc_info=True)
            return ExecutionResult(success=False, error=f"执行失败: {str(e)}")
