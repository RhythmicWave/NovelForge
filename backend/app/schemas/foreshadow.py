from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field
from app.db.models import ForeshadowItem as ForeshadowItemModel


class SuggestRequest(BaseModel):
	text: str = Field(..., description="待分析文本")

class SuggestResponse(BaseModel):
	goals: List[str]
	items: List[str]
	persons: List[str]


class ForeshadowRegisterItem(BaseModel):
	title: str
	type: str = Field('other', description='goal|item|person|other')
	note: Optional[str] = None
	chapter_id: Optional[int] = None

class ForeshadowRegisterRequest(BaseModel):
	project_id: int
	items: List[ForeshadowRegisterItem]

class ForeshadowListResponse(BaseModel):
	items: List[ForeshadowItemModel]

class ForeshadowResolveRequest(BaseModel):
	project_id: int

class ForeshadowDeleteRequest(BaseModel):
	project_id: int 