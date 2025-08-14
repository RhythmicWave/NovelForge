from __future__ import annotations

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.relation_extract import RelationExtraction
from app.schemas.entity import UpdateDynamicInfo


class IngestCardTextRequest(BaseModel):
	project_id: int = Field(..., description="项目ID")
	card_id: int = Field(..., description="卡片ID（章节正文卡）")


class QueryRequest(BaseModel):
	project_id: int
	participants: Optional[List[str]] = None
	radius: int = 2

class QueryResponse(BaseModel):
	nodes: List[Dict[str, Any]]
	edges: List[Dict[str, Any]]
	# 精简：仅保留实际使用字段
	fact_summaries: List[str]
	relation_summaries: List[Dict[str, Any]]


class IngestRelationsLLMRequest(BaseModel):
	project_id: int
	text: str
	participants: Optional[List[str]] = None
	llm_config_id: int = 1
	timeout: Optional[float] = None
	volume_number: Optional[int] = None
	chapter_number: Optional[int] = None

class IngestRelationsLLMResponse(BaseModel):
	written: int


class ExtractRelationsRequest(BaseModel):
	text: str
	participants: Optional[List[str]] = None
	llm_config_id: int = 1
	timeout: Optional[float] = None
	volume_number: Optional[int] = None
	chapter_number: Optional[int] = None


class IngestRelationsFromPreviewRequest(BaseModel):
	project_id: int
	data: RelationExtraction
	volume_number: Optional[int] = None
	chapter_number: Optional[int] = None

class IngestRelationsFromPreviewResponse(BaseModel):
	written: int


class ExtractDynamicInfoRequest(BaseModel):
	project_id: int
	text: str
	participants: Optional[List[str]] = None
	llm_config_id: int = 1
	timeout: Optional[float] = None
	extra_context: Optional[str] = None

class ExtractOnlyRequest(BaseModel):
	project_id: Optional[int] = None
	text: str
	participants: Optional[List[str]] = None
	llm_config_id: int = 1
	timeout: Optional[float] = None
	extra_context: Optional[str] = None


class UpdateDynamicInfoRequest(BaseModel):
	project_id: int
	data: UpdateDynamicInfo
	queue_size: Optional[int] = 5

class UpdateDynamicInfoResponse(BaseModel):
	success: bool
	updated_card_count: int 