from __future__ import annotations

from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field



# 扩展后的关系类型（中文枚举，保持单一来源）
RelationKind = Literal[
    # 人物关系
    '同盟','队友','同门','敌对','亲属','师徒','对手','伙伴','上级','下属','指导',
    # 人物 ↔ 组织
    '隶属','成员','领导','创立',
    # 组织 ↔ 场景
    '控制','位于',
    # 泛用与兜底
    '影响','克制','关于','其他'
]

# 统一提供中英映射（单一来源）——保留兼容（如已有英文入图/读图逻辑）
CN_TO_EN_KIND: Dict[str, str] = {
    '同盟': 'ally',
    '队友': 'team',
    '同门': 'fellow',
    '敌对': 'enemy',
    '亲属': 'family',
    '师徒': 'mentor',
    '对手': 'rival',
    '伙伴': 'partner',
    '上级': 'superior',
    '下属': 'subordinate',
    '指导': 'guide',

    '隶属': 'member_of',
    '成员': 'member',
    '领导': 'lead',
    '创立': 'found',


    '控制': 'control',
    '位于': 'locate_in',

    '影响': 'influence',
    '克制': 'counter',
    '关于': 'about',
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
    description: Optional[str] = Field(default=None, description="对该关系的简要文字说明（可选）")
    # 互相称呼（可选，无需出现在近期对话中）
    a_to_b_addressing: Optional[str] = Field(default=None, description="A 对 B 的称呼词，如：师兄、先生。仅当 A, B 均为角色时提取。")
    b_to_a_addressing: Optional[str] = Field(default=None, description="B 对 A 的称呼词。仅当 A, B 均为角色时提取。")
    # 近期证据（用于语气一致性与事实回溯）——建议各 ≤3 条
    recent_dialogues: List[str] = Field(default_factory=list, description="近期对话片段（建议包含双方各至少一句，可用 A:“…”, B:“…” 合并片段；长度≥20字）。仅当 A, B 均为角色时提取。")
    recent_event_summaries: List[RecentEventSummary] = Field(default_factory=list, description="近期 A 与 B 直接发生在彼此之间的事件；若同一事实涉及三方或以上，仅在最直接的一对上记录一次。优先记录角色-角色的配对；当事件主体确系 A 与 B 为角色-组织/组织-组织时再记录相应关系，避免将组织背景误当作双边事件。")
    # 立场（可选）：友好/中立/敌意
    stance: Optional[Literal['友好','中立','敌意']] = Field(default=None, description="A 对 B 的总体立场（可选）")


class RelationExtraction(BaseModel):
    relations: List[RelationItem] = Field(default_factory=list) 