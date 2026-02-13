from typing import Any, Dict, List, Optional, AsyncIterator, Union, TYPE_CHECKING
from loguru import logger
from pydantic import BaseModel, Field
from sqlmodel import select

if TYPE_CHECKING:
    from ...engine.async_executor import ProgressEvent

from app.db.models import Card
from app.services.card_service import CardService
from app.schemas.card import CardCreate
from ...registry import register_node
from ..base import BaseNode, get_card_type_by_name


class CardBatchUpsertInput(BaseModel):
    """批量更新卡片输入"""
    project_id: int = Field(..., description="项目ID（必须显式传递）")
    items: List[Any] = Field(..., description="数据列表（必须是list类型）")
    card_type: str = Field(
        ..., 
        description="卡片类型名称",
        json_schema_extra={"x-component": "CardTypeSelect"}
    )
    title_template: str = Field(..., description="标题模板，支持 {item.field} 语法")
    content_template: Optional[Any] = Field(default_factory=dict, description="内容模板（可选，支持 dict 或 str）")
    match_by: str = Field("title", description="匹配现有卡片的方式（默认按标题）")
    parent_id: Optional[Any] = Field(None, description="父卡片ID（支持ID数字或模板语法 {item.pid}）")


class CardBatchUpsertOutput(BaseModel):
    """批量更新卡片输出"""
    cards: List[Dict[str, Any]] = Field(..., description="处理后的卡片列表")
    output: List[int] = Field(..., description="卡片ID列表（兼容）")


@register_node
class CardBatchUpsertNode(BaseNode[CardBatchUpsertInput, CardBatchUpsertOutput]):
    """批量创建/更新卡片节点。

    严格约束（给工作流编写 Agent）：
    1) `content_template` 必须是字面量 dict，且字段与目标卡片 schema 对齐。
    2) 允许在字段值中使用 `{item.xxx}` 占位符；禁止将整个 `content_template` 设为表达式结果。
    3) 不能臆造字段，必须先确认该卡片类型可写字段。

    推荐：先查询卡片类型 schema，再编写 `title_template/content_template`。
    """
    node_type = "Card.BatchUpsert"
    category = "card"
    label = "批量更新卡片"
    description = "根据列表数据批量创建或更新卡片"
    
    input_model = CardBatchUpsertInput
    output_model = CardBatchUpsertOutput

    async def execute(self, inputs: CardBatchUpsertInput) -> AsyncIterator[Union['ProgressEvent', CardBatchUpsertOutput]]:
        """批量更新卡片（支持断点续传）"""
        from ...engine.async_executor import ProgressEvent
        
        items = inputs.items
        
        # 强制要求输入是列表
        if not isinstance(items, list):
            raise ValueError(f"items 输入必须是列表类型，当前类型: {type(items).__name__}。请使用 Data.ExtractPath 节点提取列表。")
        
        # === 1. 读取检查点 ===
        checkpoint = getattr(self.context, 'checkpoint', None)
        start_index = checkpoint.get('processed_count', 0) if checkpoint else 0
        
        if start_index > 0:
            logger.info(f"[BatchUpsert] 从检查点恢复: 已处理 {start_index}/{len(items)}")
        
        # 获取基础 parent_id 配置
        base_parent_id = inputs.parent_id
        
        # 兼容性处理：如果 parent_id 是字典（来自 Card.Read 输出），提取 id
        if isinstance(base_parent_id, dict):
            base_parent_id = base_parent_id.get("id")
        
        # 获取卡片类型
        card_type = get_card_type_by_name(self.context.session, inputs.card_type)
        if not card_type:
            raise ValueError(f"卡片类型不存在: {inputs.card_type}")

        # 使用显式传递的 project_id（不再从全局变量查找）
        project_id = inputs.project_id
        
        logger.info(
            f"[BatchUpsert] 使用显式传递的项目ID: project_id={project_id}"
        )

        results = []
        service = CardService(self.context.session)
        total = len(items)
        
        # === 2. 从检查点继续处理 ===
        for index in range(start_index, total):
            item = items[index]
            
            # 准备模版上下文
            ctx = {"item": item, "index": index + 1}
            
            # 渲染标题
            try:
                title = self._render_template(inputs.title_template, ctx)
            except Exception as e:
                logger.warning(f"[BatchUpsert] 标题渲染失败: {e}")
                continue
                
            if not title:
                continue

            # 计算当前项的 parent_id
            current_parent_id = None
            if base_parent_id is not None:
                if isinstance(base_parent_id, int):
                    current_parent_id = base_parent_id
                elif isinstance(base_parent_id, str):
                    if '{' in base_parent_id and '}' in base_parent_id:
                        # 模板渲染
                        rendered = self._render_template(base_parent_id, ctx)
                        # 尝试转 int
                        if rendered and rendered.isdigit():
                            current_parent_id = int(rendered)
                        else:
                            # 渲染结果为空或非数字，视为无父级或无效
                            current_parent_id = None 
                    elif base_parent_id.isdigit():
                         current_parent_id = int(base_parent_id)
            
            # 查找现有卡片
            stmt = select(Card).where(
                Card.project_id == project_id,
                Card.card_type_id == card_type.id,
                Card.title == title
            )
            if current_parent_id:
                stmt = stmt.where(Card.parent_id == current_parent_id)
            
            existing_card = self.context.session.exec(stmt).first()
            
            # 渲染内容
            content = {}
            if inputs.content_template:
                rendered_content = self._render_content(inputs.content_template, ctx)
                # 确保 content 是字典类型
                if isinstance(rendered_content, dict):
                    content = rendered_content
                elif rendered_content:  # 非空但不是字典，包装成字典
                    content = {"value": rendered_content}
                # 如果是空字符串或 None，保持 content 为空字典
            elif isinstance(item, dict):
                 # 如果没有模板且 item 是 dict，默认使用 item 作为内容
                 content = item
            
            if existing_card:
                # 更新
                updated = False
                if content:
                    # 简单合并
                    if not isinstance(existing_card.content, dict):
                        existing_card.content = {}
                    existing_card.content.update(content)
                    updated = True
                
                # 如果父ID变化（移动）
                if current_parent_id and existing_card.parent_id != current_parent_id:
                    existing_card.parent_id = current_parent_id
                    updated = True
                    
                if updated:
                    self.context.session.add(existing_card)
                    # 手动提交更新
                    self.context.session.commit()
                    self.context.session.refresh(existing_card)
                    results.append(existing_card)
                else:
                    results.append(existing_card)
            else:
                # 创建
                try:
                    card_create = CardCreate(
                        title=title,
                        content=content,
                        card_type_id=card_type.id,
                        parent_id=current_parent_id,
                        project_id=project_id
                    )
                    
                    new_card = service.create(card_create, project_id)
                    results.append(new_card)
                except Exception as e:
                    logger.error(f"[BatchUpsert] 创建卡片失败: {e}")
                    continue
            
            # === 3. 报告进度（自动保存检查点）===
            percent = ((index + 1) / total) * 100
            yield ProgressEvent(
                percent=percent,
                message=f"已处理 {index + 1}/{total} 张卡片",
                data={
                    'processed_count': index + 1,  # ✅ 轻量级：计数器
                    'last_title': title            # ✅ 轻量级：标识符
                }
            )
        
        self.context.session.commit()
        
        # 刷新以获取ID
        touched = self.context.variables.setdefault("touched_card_ids", [])
        for card in results:
            self.context.session.refresh(card)
            if card.id not in touched:
                touched.append(card.id)

        logger.info(f"[BatchUpsert] 批量处理完成: {len(results)} 个卡片 ({inputs.card_type})")
        
        # === 4. 返回最终结果 ===
        yield CardBatchUpsertOutput(
            cards=[
                {
                    "id": c.id,
                    "title": c.title,
                    "content": c.content,
                    "parent_id": c.parent_id
                } for c in results
            ],
            output=[c.id for c in results]  # 兼容性输出
        )

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """简单的字符串模版渲染 {a.b}"""
        # 简单实现，支持 {item.field}
        # 更复杂的可以使用 jinja2，这里先手写一个简单的
        import re
        
        def replace(match):
            path = match.group(1).strip()
            # 解析路径 item.name
            parts = path.split('.')
            value = context
            try:
                for part in parts:
                    if isinstance(value, dict):
                        value = value.get(part)
                    elif hasattr(value, part):
                        value = getattr(value, part)
                    else:
                        value = None
                        break
                return str(value) if value is not None else ""
            except Exception:
                return ""

        return re.sub(r'\{([^}]+)\}', replace, template)

    def _render_content(self, template: Any, context: Dict[str, Any]) -> Any:
        "递归渲染内容"
        if isinstance(template, str):
            # 只有包含 {} 才尝试渲染
            if '{' in template and '}' in template:
                # 特殊处理：如果是单一路径引用（如 {item.ai_result}），返回原始对象
                import re
                single_path_match = re.fullmatch(r'\{([^}]+)\}', template)
                if single_path_match:
                    path = single_path_match.group(1).strip()
                    parts = path.split('.')
                    value = context
                    try:
                        for part in parts:
                            if isinstance(value, dict):
                                value = value.get(part)
                            elif hasattr(value, part):
                                value = getattr(value, part)
                            else:
                                value = None
                                break
                        # 如果解析成功，返回原始对象
                        if value is not None:
                            return value
                    except Exception:
                        pass
                
                # Fallback：正常字符串渲染
                return self._render_template(template, context)
            return template
        elif isinstance(template, dict):
            return {k: self._render_content(v, context) for k, v in template.items()}
        elif isinstance(template, list):
            return [self._render_content(v, context) for v in template]
        else:
            return template
