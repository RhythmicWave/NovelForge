from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


QualityGate = Literal["pass", "revise", "block"]
ReviewType = Literal["chapter", "stage", "card", "custom"]
TargetType = Literal["card"]


class ReviewResultCardContent(BaseModel):
    review_target_card_id: int = Field(description="被审核卡片 ID")
    review_target_title: str = Field(description="被审核卡片标题")
    review_target_type: TargetType = Field(default="card", description="被审核目标类型")
    review_type: ReviewType = Field(default="card", description="审核类型")
    review_profile: str = Field(description="审核 profile code")
    review_target_field: Optional[str] = Field(default=None, description="被审核字段路径")
    quality_gate: QualityGate = Field(description="审核结论")
    review_markdown: str = Field(description="审核结果正文（Markdown）")
    prompt_name: str = Field(description="使用的提示词名称")
    llm_config_id: Optional[int] = Field(default=None, description="审核所用模型配置")
    reviewed_at: str = Field(description="审核时间（ISO 格式字符串）")
    target_snapshot: Optional[str] = Field(default=None, description="被审核内容快照")
    meta: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")


class ReviewResultCardRead(BaseModel):
    card_id: int
    project_id: int
    title: str
    review_target_card_id: int
    review_target_title: str
    review_target_type: TargetType = "card"
    review_type: ReviewType
    review_profile: str
    review_target_field: Optional[str] = None
    quality_gate: QualityGate
    review_markdown: str
    prompt_name: str
    llm_config_id: Optional[int] = None
    reviewed_at: str
    target_snapshot: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ReviewDraftResult(BaseModel):
    review_text: str
    quality_gate: QualityGate
    review_type: ReviewType
    review_profile: str
    review_target_field: Optional[str] = None
    prompt_name: str
    llm_config_id: Optional[int] = None
    target_snapshot: Optional[str] = None
    existing_review_card_id: Optional[int] = None
    review_card_title: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class ReviewRunRequest(BaseModel):
    card_id: int
    project_id: Optional[int] = None
    title: str
    target_type: TargetType = Field(default="card")
    review_type: ReviewType = Field(default="card")
    review_profile: str = Field(default="generic_card_review")
    target_field: str = Field(default="content")
    target_text: Optional[str] = None
    context_info: Optional[str] = None
    facts_info: Optional[str] = None
    content_snapshot: Optional[str] = Field(default=None, description="可选存储的审核目标快照")
    llm_config_id: int
    prompt_name: str = Field(default="通用审核")
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout: Optional[float] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ReviewCardUpsertRequest(BaseModel):
    project_id: int
    target_card_id: int
    target_title: str
    review_type: ReviewType
    review_profile: str
    target_field: Optional[str] = None
    review_text: str
    quality_gate: QualityGate
    prompt_name: str
    llm_config_id: Optional[int] = None
    content_snapshot: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ReviewRunResponse(BaseModel):
    review_text: str
    draft: ReviewDraftResult
