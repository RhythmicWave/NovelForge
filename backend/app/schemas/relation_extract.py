from __future__ import annotations

from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field



RelationKind = Literal['同盟','队友','同门','敌对','亲属','师徒','对手','隶属','其他']

# 统一提供中英映射（单一来源）
CN_TO_EN_KIND: Dict[str, str] = {
    '同盟': 'ally',
    '队友': 'team',
    '同门': 'fellow',
    '敌对': 'enemy',
    '亲属': 'family',
    '师徒': 'mentor',
    '对手': 'rival',
    '隶属': 'member_of',
    '其他': 'other',
}
EN_TO_CN_KIND: Dict[str, str] = {v: k for k, v in CN_TO_EN_KIND.items()}


class RecentEventSummary(BaseModel):
    summary: str = Field(description="A、B 之间近期发生事件的一句摘要（本次提取建议融合为一条）")
    volume_number: Optional[int] = Field(default=None, description="发生的卷号（置空，系统可补全）")
    chapter_number: Optional[int] = Field(default=None, description="发生的章节号（置空，系统可补全）")


class RelationItem(BaseModel):
    a: str = Field(description="实体 A 名称（参与者之一）")
    b: str = Field(description="实体 B 名称（参与者之一）")
    kind: RelationKind = Field(description="关系类型（中文）")
    # 互相称呼（可选，无需出现在近期对话中）
    a_to_b_addressing: Optional[str] = Field(default=None, description="A 对 B 的称呼词，如：师兄、先生")
    b_to_a_addressing: Optional[str] = Field(default=None, description="B 对 A 的称呼词")
    # 近期证据（用于语气一致性与事实回溯）
    recent_dialogues: List[str] = Field(default_factory=list, description="近期对话片段（建议包含双方各至少一句，可用 A:“…”, B:“…” 合并片段；长度≥20字）")
    recent_event_summaries: List[RecentEventSummary] = Field(default_factory=list, description="近期 A、B 之间发生事件（本次提取建议融合为一条）")


class RelationExtraction(BaseModel):
    relations: List[RelationItem] = Field(default_factory=list) 