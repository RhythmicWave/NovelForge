from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.relation_extract import RelationItem


class AssembleContextRequest(BaseModel):
	project_id: Optional[int] = Field(default=None, description="项目ID")
	volume_number: Optional[int] = Field(default=None, description="卷号")
	chapter_number: Optional[int] = Field(default=None, description="章节号")
	chapter_id: Optional[int] = Field(default=None, description="章节卡片ID（可选）")
	participants: Optional[List[str]] = Field(default=None, description="参与实体名称列表")
	current_draft_tail: Optional[str] = Field(default=None, description="上下文模板（草稿尾部）")
	recent_chapters_window: Optional[int] = Field(default=None, description="最近窗口（保留，将来扩展）")


class ItemSummary(BaseModel):
	name: str = Field(..., description="物品名称")
	category: str = Field(default="", description="物品类别")
	description: str = Field(default="", description="物品简介")
	owner_hint: Optional[str] = Field(default=None, description="持有者提示")
	current_state: Optional[str] = Field(default=None, description="当前状态")
	power_or_effect: Optional[str] = Field(default=None, description="能力或用途")
	constraints: Optional[str] = Field(default=None, description="限制条件")
	important_events: List[str] = Field(default_factory=list, description="重要事件")


class ConceptSummary(BaseModel):
	name: str = Field(..., description="概念名称")
	category: str = Field(default="", description="概念类别")
	description: str = Field(default="", description="概念简介")
	rule_definition: str = Field(default="", description="规则定义")
	cost: Optional[str] = Field(default=None, description="代价或成本")
	mastery_hint: Optional[str] = Field(default=None, description="掌握提示")
	known_by: List[str] = Field(default_factory=list, description="已知掌握者")
	counter_relations: List[str] = Field(default_factory=list, description="对立或克制关系")


class FactsStructured(BaseModel):
	fact_summaries: List[str] = Field(default_factory=list, description="关键事实摘要")
	relation_summaries: List[RelationItem] = Field(default_factory=list, description="关系摘要（含近期对话/事件）")
	item_summaries: List[ItemSummary] = Field(default_factory=list, description="物品摘要")
	concept_summaries: List[ConceptSummary] = Field(default_factory=list, description="概念摘要")


class AssembleContextResponse(BaseModel):
	facts_subgraph: str = Field(default="", description="事实子图的文本回显（可选，仅回显）")
	budget_stats: Dict[str, Any] = Field(default_factory=dict, description="上下文字数预算统计（可能包含嵌套 parts dict）")
	facts_structured: Optional[FactsStructured] = Field(default=None, description="结构化事实子图")


class ContextSettingsModel(BaseModel):
	recent_chapters_window: int
	total_context_budget_chars: int
	soft_budget_chars: int
	quota_recent: int
	quota_older_summary: int
	quota_facts: int


class UpdateContextSettingsRequest(BaseModel):
	recent_chapters_window: Optional[int] = None
	total_context_budget_chars: Optional[int] = None
	soft_budget_chars: Optional[int] = None
	quota_recent: Optional[int] = None
	quota_older_summary: Optional[int] = None
	quota_facts: Optional[int] = None
