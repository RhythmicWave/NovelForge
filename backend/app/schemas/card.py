from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


# --- CardType Schemas ---

class CardTypeBase(BaseModel):
    name: str
    description: Optional[str] = None
    # 新增：统一选择的输出模型名称（对应 OutputModel.name）
    output_model_name: Optional[str] = None
    editor_component: Optional[str] = None
    is_ai_enabled: bool = Field(default=False)
    is_singleton: bool = Field(default=False)
    # 新增：默认AI上下文注入模板（类型级别）
    default_ai_context_template: Optional[str] = None
    # 新增：UI 布局（可选）
    ui_layout: Optional[Dict[str, Any]] = None


class CardTypeCreate(CardTypeBase):
    pass


class CardTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    output_model_name: Optional[str] = None
    editor_component: Optional[str] = None
    is_ai_enabled: Optional[bool] = None
    is_singleton: Optional[bool] = None
    default_ai_context_template: Optional[str] = None
    ui_layout: Optional[Dict[str, Any]] = None


class CardTypeRead(CardTypeBase):
    id: int
    built_in: bool = False


# --- Card Schemas ---

class CardBase(BaseModel):
    title: str
    content: Optional[Dict[str, Any]] = Field(default_factory=dict)
    parent_id: Optional[int] = None
    card_type_id: int


class CardCreate(CardBase):
    pass


class CardUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    parent_id: Optional[int] = None
    display_order: Optional[int] = None
    ai_context_template: Optional[str] = None
    selected_ai_param_card_id: Optional[str] = None


class CardRead(CardBase):
    id: int
    project_id: int
    created_at: datetime
    display_order: int
    card_type: CardTypeRead
    # 具体卡片可覆盖类型默认模板
    ai_context_template: Optional[str] = None 
    selected_ai_param_card_id: Optional[str] = None 