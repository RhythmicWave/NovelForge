from __future__ import annotations

from typing import Dict, Any

# 统一集中导出所有需要在 OpenAPI 中暴露的响应/嵌套模型
from app.schemas.wizard import (
	WorldBuilding, Blueprint,
	VolumeOutline, ChapterOutline,
	SpecialAbilityResponse, OneSentence, ParagraphOverview,
	CharacterCard, SceneCard, StoryLine, StageLine, 
	Tags, WorldviewTemplate, Chapter,
 WritingGuide
)
from app.schemas.entity import OrganizationCard


RESPONSE_MODEL_MAP: Dict[str, Any] = {
	'Tags': Tags,
	'SpecialAbilityResponse': SpecialAbilityResponse,
	'OneSentence': OneSentence,
	'ParagraphOverview': ParagraphOverview,
	'WorldBuilding': WorldBuilding,
	'WorldviewTemplate': WorldviewTemplate,
	'Blueprint': Blueprint,
	# 使用未包装模型
	'VolumeOutline': VolumeOutline,
 	'WritingGuide': WritingGuide,
	'ChapterOutline': ChapterOutline,
	'Chapter': Chapter,
	# 基础schema，自动包含在OpenAPI中
	'CharacterCard': CharacterCard,
	'SceneCard': SceneCard,
	'OrganizationCard': OrganizationCard,
	# 显式导出嵌套类型，便于前端字段树解析
	'StageLine': StageLine,
	'StoryLine': StoryLine,
} 