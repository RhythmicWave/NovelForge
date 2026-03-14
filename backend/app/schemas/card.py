from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator
from datetime import datetime


# --- CardType Schemas ---

class CardTypeBase(BaseModel):
    name: str
    model_name: Optional[str] = None
    description: Optional[str] = None
    # 类型内置结构（JSON Schema）
    json_schema: Optional[Dict[str, Any]] = None
    # 类型默认 AI 参数
    ai_params: Optional[Dict[str, Any]] = None
    editor_component: Optional[str] = None
    is_ai_enabled: bool = Field(default=False)
    is_singleton: bool = Field(default=False)
    # 默认AI上下文注入模板（类型级别）
    default_ai_context_template: Optional[str] = None
    default_ai_context_template_review: Optional[str] = None
    # UI 布局（可选）
    ui_layout: Optional[Dict[str, Any]] = None


class CardTypeCreate(CardTypeBase):
    pass


class CardTypeUpdate(BaseModel):
    name: Optional[str] = None
    model_name: Optional[str] = None
    description: Optional[str] = None
    json_schema: Optional[Dict[str, Any]] = None
    ai_params: Optional[Dict[str, Any]] = None
    editor_component: Optional[str] = None
    is_ai_enabled: Optional[bool] = None
    is_singleton: Optional[bool] = None
    default_ai_context_template: Optional[str] = None
    default_ai_context_template_review: Optional[str] = None
    ui_layout: Optional[Dict[str, Any]] = None


class CardTypeRead(CardTypeBase):
    id: int
    built_in: bool = False


# --- Card Schemas ---

class CardBase(BaseModel):
    title: str
    model_name: Optional[str] = None
    content: Optional[Dict[str, Any]] = Field(default_factory=dict)
    parent_id: Optional[int] = None
    card_type_id: int
    # 实例可选自定义结构；为空表示跟随类型
    json_schema: Optional[Dict[str, Any]] = None
    # 实例 AI 参数；为空表示跟随类型
    ai_params: Optional[Dict[str, Any]] = None
    ai_context_template: Optional[str] = None
    ai_context_template_review: Optional[str] = None


class CardCreate(CardBase):
    pass


class CardUpdate(BaseModel):
    title: Optional[str] = None
    model_name: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    parent_id: Optional[int] = None
    display_order: Optional[int] = None
    ai_context_template: Optional[str] = None
    ai_context_template_review: Optional[str] = None
    json_schema: Optional[Dict[str, Any]] = None
    ai_params: Optional[Dict[str, Any]] = None
    # AI 修改追踪字段（前端需要清除 needs_confirmation）
    needs_confirmation: Optional[bool] = None


class CardRead(CardBase):
    id: int
    project_id: int
    created_at: datetime
    display_order: int
    card_type: CardTypeRead
    # 具体卡片可覆盖类型默认模板
    ai_context_template: Optional[str] = None
    ai_context_template_review: Optional[str] = None
    # AI 修改追踪字段
    ai_modified: bool = False
    needs_confirmation: bool = False
    last_modified_by: Optional[str] = None


# --- Operations ---

class CardCopyOrMoveRequest(BaseModel):
    target_project_id: int
    parent_id: Optional[int] = None


class CardOrderItem(BaseModel):
    """单个卡片的排序信息"""
    card_id: int
    display_order: int
    parent_id: Optional[int] = None


class CardBatchReorderRequest(BaseModel):
    """批量更新卡片排序请求"""
    updates: List[CardOrderItem] = Field(description="要更新的卡片排序列表") 


# --- Export ---

CardExportScope = Literal["all", "single", "type"]
CardExportFormat = Literal["txt", "md", "json"]


class CardExportRequest(BaseModel):
    """项目卡片导出请求"""

    scope: CardExportScope = Field(default="all", description="导出范围")
    card_id: Optional[int] = Field(default=None, description="单卡导出时的卡片ID")
    card_type_id: Optional[int] = Field(default=None, description="按类型导出时的卡片类型ID")
    format: CardExportFormat = Field(default="txt", description="导出格式")

    @model_validator(mode="after")
    def validate_scope_fields(self):
        if self.scope == "single" and self.card_id is None:
            raise ValueError("scope=single 时必须提供 card_id")
        if self.scope == "type" and self.card_type_id is None:
            raise ValueError("scope=type 时必须提供 card_type_id")
        return self
