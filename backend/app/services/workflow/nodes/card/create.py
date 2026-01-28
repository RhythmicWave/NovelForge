from typing import Any, Dict, Optional
from loguru import logger
from pydantic import Field

from app.db.models import Card
from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig, get_card_type_by_name


class CardCreateConfig(BaseNodeConfig):
    card_type: str = Field(..., description="卡片类型名称")
    title: Optional[str] = Field(None, description="卡片标题（可选，可由输入提供）")
    content: Optional[Dict[str, Any]] = Field(default_factory=dict, description="卡片内容（可选，可由输入提供）")
    project_id: Optional[int] = Field(None, description="项目ID（可选，默认从触发数据获取）")


@register_node
class CardCreateNode(BaseNode):
    node_type = "Card.Create"
    category = "card"
    label = "创建卡片"
    description = "创建新卡片"
    config_model = CardCreateConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("parent", "card", required=False, description="父卡片"),
                NodePort("title", "string", required=False, description="标题（覆盖配置）"),
                NodePort("content", "object", required=False, description="内容（合并/覆盖配置）")
            ],
            "outputs": [
                NodePort("card", "card", description="创建的卡片"),
                NodePort("output", "card", description="卡片对象 (兼容)")
            ]
        }

    async def execute(self, inputs: Dict[str, Any], config: CardCreateConfig) -> ExecutionResult:
        """创建卡片节点"""
        # 1. 准备数据 (输入优先)
        title = inputs.get("title") or config.title
        if not title:
             return ExecutionResult(success=False, error="未提供卡片标题")

        content = config.content.copy() if config.content else {}
        if inputs.get("content"):
            content.update(inputs["content"])
        
        # 检查卡片类型
        card_type = get_card_type_by_name(self.context.session, config.card_type)
        if not card_type:
            return ExecutionResult(
                success=False,
                error=f"卡片类型不存在: {config.card_type}"
            )
        
        # 获取项目ID
        project_id = config.project_id
        if not project_id:
            # 尝试从变量或范围中获取
            project_id = self.context.variables.get("project_id")
            if not project_id:
                scope = self.context.variables.get("scope", {})
                project_id = scope.get("project_id")
            if not project_id:
                # 尝试从上下文获取
                project_id = self.context.variables.get("project_id")
                if not project_id:
                    trigger = self.context.variables.get("trigger", {})
                    project_id = trigger.get("project_id")
        
        if not project_id:
            return ExecutionResult(
                success=False,
                error="未指定项目ID"
            )
        
        parent_data = inputs.get("parent", {})
        parent_id = parent_data.get("id")
        
        # 使用 CardService 创建卡片（复用其逻辑：自动处理标题冲突、默认上下文模板、display_order等）
        from app.services.card_service import CardService
        from app.schemas.card import CardCreate
        
        card_service = CardService(self.context.session)
        
        try:
            card_in = CardCreate(
                title=title,
                content=content,
                card_type_id=card_type.id,
                parent_id=parent_id,
                project_id=project_id  # CardCreate 虽然没这个字段，但 create 方法参数需要
                # ai_context_template 留空，让 Service 按 rules 处理
            )
            # Service.create(card_create: CardCreate, project_id: int)
            card = card_service.create(card_in, project_id)
            
            # 由于 CardService.create 会 commit，这里不再需要显式 commit
            # 但为了保险（如果在事务中），我们可以继续保持 session 状态
        except Exception as e:
            logger.error(f"[Card.Create] 创建失败: {e}")
            return ExecutionResult(success=False, error=str(e))
        
        # 记录受影响的卡片
        self.context.variables.setdefault("touched_card_ids", set()).add(card.id)
        
        # 记录补偿日志（用于回滚）
        from ...engine.state_manager import StateManager
        state_manager = StateManager(self.context.session)
        state_manager.add_compensation_log(
            run_id=self.context.run_id,
            operation="card.created",
            card_id=card.id
        )
        
        logger.info(
            f"[Card.Create] 创建卡片: id={card.id}, title={card.title}, "
            f"type={config.card_type}"
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
                },
                "output": { # 兼容性输出：完整对象
                    "id": card.id,
                    "title": card.title,
                    "content": card.content,
                    "card_type_id": card.card_type_id,
                    "parent_id": card.parent_id
                }
            }
        )
