from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field
from sqlmodel import SQLModel


QualityGate = Literal["pass", "revise", "block"]
ReviewType = Literal["chapter", "stage"]
TargetType = Literal["card"]


class PreviousChapterInput(BaseModel):
    title: str
    volume_number: Optional[int] = None
    chapter_number: Optional[int] = None
    content: str = ""


class PreviousStageInput(BaseModel):
    title: str
    stage_name: Optional[str] = None
    volume_number: Optional[int] = None
    stage_number: Optional[int] = None
    reference_chapter: List[int] = Field(default_factory=list)
    overview: str = ""
    analysis: Optional[str] = None
    entity_snapshot: List[str] = Field(default_factory=list)


class StageChapterOutlineInput(BaseModel):
    title: str
    chapter_number: Optional[int] = None
    overview: str = ""
    entity_list: List[str] = Field(default_factory=list)
    has_content: bool = False
    word_count: Optional[int] = None


class ChapterReviewRunRequest(BaseModel):
    card_id: int
    project_id: Optional[int] = None
    title: str
    chapter_content: str
    volume_number: Optional[int] = None
    chapter_number: Optional[int] = None
    participants: List[str] = Field(default_factory=list)
    previous_chapters: List[PreviousChapterInput] = Field(default_factory=list)
    context_info: Optional[str] = None
    facts_info: Optional[str] = None
    content_snapshot: Optional[str] = Field(default=None, description="可选存储的正文快照")
    llm_config_id: int
    prompt_name: str = Field(default="章节审核")
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout: Optional[float] = None


class StageReviewRunRequest(BaseModel):
    card_id: int
    project_id: Optional[int] = None
    title: str
    stage_name: Optional[str] = None
    volume_number: Optional[int] = None
    stage_number: Optional[int] = None
    reference_chapter: List[int] = Field(default_factory=list)
    analysis: Optional[str] = None
    overview: Optional[str] = None
    entity_snapshot: List[str] = Field(default_factory=list)
    chapter_outlines: List[StageChapterOutlineInput] = Field(default_factory=list)
    previous_stages: List[PreviousStageInput] = Field(default_factory=list)
    context_info: Optional[str] = None
    facts_info: Optional[str] = None
    content_snapshot: Optional[str] = Field(default=None, description="可选存储的阶段快照")
    llm_config_id: int
    prompt_name: str = Field(default="阶段审核")
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout: Optional[float] = None


class ReviewRecordRead(SQLModel):
    id: int
    project_id: int
    review_type: ReviewType
    target_type: TargetType
    target_id: int
    target_title: Optional[str] = None
    prompt_name: str
    llm_config_id: Optional[int] = None
    quality_gate: str
    result_text: str
    content_snapshot: Optional[str] = None
    created_at: datetime


class ChapterReviewRunResponse(BaseModel):
    review_text: str
    record: ReviewRecordRead


class StageReviewRunResponse(BaseModel):
    review_text: str
    record: ReviewRecordRead
