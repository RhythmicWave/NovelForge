from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.relation_extract import RelationKind, RelationStance


CsvJsonFormat = Literal["json", "csv"]


class RelationGraphEvent(BaseModel):
    summary: str = Field(description="事件摘要")
    volume_number: Optional[int] = Field(default=None, description="卷号")
    chapter_number: Optional[int] = Field(default=None, description="章节号")


class RelationGraphKey(BaseModel):
    source: str = Field(description="关系起点实体")
    target: str = Field(description="关系终点实体")
    kind_en: str = Field(description="关系英文键")


class RelationGraphInput(BaseModel):
    source: str = Field(description="关系起点实体")
    target: str = Field(description="关系终点实体")
    kind_en: Optional[str] = Field(default=None, description="关系英文键")
    kind_cn: Optional[RelationKind] = Field(default=None, description="关系中文类型")
    kind: Optional[RelationKind] = Field(default=None, description="关系中文类型（兼容字段）")
    fact: Optional[str] = Field(default=None, description="关系事实描述")
    description: Optional[str] = Field(default=None, description="关系描述")
    a_to_b_addressing: Optional[str] = Field(default=None, description="A 对 B 称呼")
    b_to_a_addressing: Optional[str] = Field(default=None, description="B 对 A 称呼")
    recent_dialogues: List[str] = Field(default_factory=list, description="近期对话证据")
    recent_event_summaries: List[RelationGraphEvent] = Field(default_factory=list, description="近期事件证据")
    stance: Optional[RelationStance] = Field(default=None, description="立场：友好/中立/敌意")


class RelationGraphRecord(BaseModel):
    source: str
    target: str
    kind_en: str
    kind_cn: RelationKind
    kind: RelationKind
    fact: str
    a_to_b_addressing: Optional[str] = None
    b_to_a_addressing: Optional[str] = None
    recent_dialogues: List[str] = Field(default_factory=list)
    recent_event_summaries: List[RelationGraphEvent] = Field(default_factory=list)
    stance: Optional[RelationStance] = None
    updated_at: Optional[str] = None


class RelationGraphListRequest(BaseModel):
    project_id: int
    keyword: Optional[str] = None
    kinds: List[RelationKind] = Field(default_factory=list)
    stances: List[RelationStance] = Field(default_factory=list)
    offset: int = 0
    limit: int = 50


class RelationGraphListResponse(BaseModel):
    items: List[RelationGraphRecord] = Field(default_factory=list)
    total: int = 0


class RelationGraphUpsertRequest(BaseModel):
    project_id: int
    relation: RelationGraphInput


class RelationGraphDeleteRequest(BaseModel):
    project_id: int
    key: RelationGraphKey


class RelationGraphBatchDeleteRequest(BaseModel):
    project_id: int
    keys: List[RelationGraphKey] = Field(default_factory=list)


class RelationGraphBatchUpdateKindRequest(BaseModel):
    project_id: int
    keys: List[RelationGraphKey] = Field(default_factory=list)
    new_kind_en: Optional[str] = Field(default=None, description="新的关系英文键")
    new_kind_cn: Optional[RelationKind] = Field(default=None, description="新的关系中文类型")


class RelationGraphBatchUpdateStanceRequest(BaseModel):
    project_id: int
    keys: List[RelationGraphKey] = Field(default_factory=list)
    stance: Optional[RelationStance] = Field(default=None, description="新立场")


class RelationGraphBatchAppendEventsRequest(BaseModel):
    project_id: int
    keys: List[RelationGraphKey] = Field(default_factory=list)
    events: List[RelationGraphEvent] = Field(default_factory=list)
    max_size: int = 20


class RelationGraphBatchCreateRequest(BaseModel):
    project_id: int
    relations: List[RelationGraphInput] = Field(default_factory=list)


class RelationGraphWriteResponse(BaseModel):
    affected: int = 0


class RelationGraphExportRequest(BaseModel):
    project_id: int
    format: CsvJsonFormat = "json"
    keys: List[RelationGraphKey] = Field(default_factory=list)


class RelationGraphExportResponse(BaseModel):
    filename: str
    mime_type: str
    content: str


class RelationGraphImportRequest(BaseModel):
    project_id: int
    format: CsvJsonFormat = "json"
    content: str


class RelationGraphImportResponse(BaseModel):
    created: int = 0
    updated: int = 0
    failed: int = 0
    errors: List[str] = Field(default_factory=list)


class RelationGraphKindOption(BaseModel):
    kind_cn: RelationKind
    kind_en: str


class RelationGraphMetaResponse(BaseModel):
    kinds: List[RelationGraphKindOption] = Field(default_factory=list)
    stances: List[RelationStance] = Field(default_factory=list)
