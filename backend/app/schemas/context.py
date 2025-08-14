from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.relation_extract import RelationItem


class AssembleContextRequest(BaseModel):
	project_id: Optional[int] = Field(default=None, description="项目ID")
	volume_number: Optional[int] = Field(default=None, description="卷号")
	chapter_number: Optional[int] = Field(default=None, description="章节号")
	chapter_id: Optional[int] = Field(default=None, description="章节卡片ID（可选）")
	participants: Optional[List[str]] = Field(default=None, description="参与实体名称列表")
	current_draft_tail: Optional[str] = Field(default=None, description="上下文模板（草稿尾部）")
	recent_chapters_window: Optional[int] = Field(default=None, description="最近窗口N（保留，为将来扩展）")


class FactsStructured(BaseModel):
	# 精简：只保留当前确实使用的字段
	fact_summaries: List[str] = Field(default_factory=list, description="关键事实摘要")
	relation_summaries: List[RelationItem] = Field(default_factory=list, description="关系摘要（含近期对话/事件）")


class AssembleContextResponse(BaseModel):
	# 精简：仅保留事实子图及预算信息
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