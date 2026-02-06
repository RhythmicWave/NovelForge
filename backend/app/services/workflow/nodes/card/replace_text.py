"""Card.ReplaceFieldText 节点

替换卡片字段中的指定文本片段（支持模糊匹配）
"""

from typing import Any, Dict, Optional, AsyncIterator
from loguru import logger
from pydantic import BaseModel, Field

from app.services.card_service import CardService
from ...registry import register_node
from ..base import BaseNode


# ============================================================
# Input/Output Models
# ============================================================

class ReplaceTextInput(BaseModel):
    """替换文本输入"""
    card_id: int = Field(..., description="目标卡片ID", gt=0)
    field_path: str = Field(..., description="字段路径 (如 content.overview)")
    old_text: str = Field(..., description="要修改的旧文本")
    new_text: str = Field("", description="新文本")


class ReplaceTextOutput(BaseModel):
    """替换文本输出"""
    card: Dict[str, Any] = Field(..., description="更新后的卡片")
    replaced_count: int = Field(..., description="替换次数")
    success: bool = Field(..., description="是否成功")


# ============================================================
# Node Implementation
# ============================================================

@register_node
class CardReplaceTextNode(BaseNode[ReplaceTextInput, ReplaceTextOutput]):
    node_type = "Card.ReplaceFieldText"
    category = "card"
    label = "替换文本"
    description = "替换卡片字段中的指定文本片段（支持模糊匹配）"
    
    input_model = ReplaceTextInput
    output_model = ReplaceTextOutput

    async def execute(self, input_data: ReplaceTextInput) -> AsyncIterator[ReplaceTextOutput]:
        """执行文本替换"""
        
        service = CardService(self.context.session)
        result = service.replace_field_text(
            card_id=input_data.card_id,
            field_path=input_data.field_path,
            old_text=input_data.old_text,
            new_text=input_data.new_text,
            fuzzy_match=True
        )
        
        if not result["success"]:
            raise ValueError(result.get("error", "替换失败"))

        # 记录受影响卡片
        touched = self.context.variables.setdefault("touched_card_ids", [])
        if input_data.card_id not in touched:
            touched.append(input_data.card_id)
        
        # 获取最新卡片对象返回
        updated_card = self.get_card_by_id(input_data.card_id)
        
        yield ReplaceTextOutput(
            card=updated_card,
            replaced_count=result.get("replaced_count", 0),
            success=True
        )

