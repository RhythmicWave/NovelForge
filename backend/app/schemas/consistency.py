from __future__ import annotations

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class CheckRequest(BaseModel):
	text: str = Field(..., description="待校验文本")
	facts_structured: Optional[Dict[str, Any]] = Field(default=None, description="结构化事实子图（relation_summaries等）")


class Issue(BaseModel):
	type: str
	message: str
	position: List[int] | None = None


class FixSuggestion(BaseModel):
	range: List[int] | None = None
	replacement: str


class CheckResponse(BaseModel):
	issues: List[Issue]
	suggested_fixes: List[FixSuggestion] 