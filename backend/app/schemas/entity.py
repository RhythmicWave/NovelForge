from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, field_validator

DynamicInfoType = Literal[
    "系统/模拟器/金手指信息",
    "等级/修为境界",
    "装备/法宝",
    "知识/情报",
    "资产/领地",
    "功法/技能",
    "血脉/体质",
    "心理想法/目标快照",
]

DYNAMIC_INFO_TYPES: List[str] = [
    "系统/模拟器/金手指信息",
    "等级/修为境界",
    "装备/法宝",
    "知识/情报",
    "资产/领地",
    "功法/技能",
    "血脉/体质",
    "心理想法/目标快照",
]

EntityType = Literal["character", "scene", "organization", "item", "concept"]


class DynamicInfoItem(BaseModel):
    id: int = Field(-1, description="手动设置，无需生成；并入时若为 -1 将自动分配顺序号")
    info: str = Field(description="简要描述具体动态信息")


class DynamicInfo(BaseModel):
    name: str = Field(description="角色名称")
    dynamic_info: Dict[DynamicInfoType, List[DynamicInfoItem]] = Field(
        default_factory=dict,
        description="动态信息字典，键为中文类别，值为信息项列表",
    )

    @staticmethod
    def _normalize_dynamic_info_dict(v: Any) -> Dict[str, Any]:
        if not isinstance(v, dict):
            return {}
        normalized: Dict[str, Any] = {}
        allowed = set(DYNAMIC_INFO_TYPES)
        for k, arr in v.items():
            key = k if isinstance(k, str) else str(k)
            if key in allowed:
                normalized[key] = arr
        return normalized

    @field_validator("dynamic_info", mode="before")
    @classmethod
    def _normalize_keys(cls, v: Any) -> Dict[str, Any]:
        return cls._normalize_dynamic_info_dict(v)


class DeletionInfo(BaseModel):
    name: str = Field(description="角色名称")
    dynamic_type: DynamicInfoType = Field(description="动态信息类型")
    id: int = Field(gt=0, description="要删除的动态信息 ID")


class UpdateDynamicInfo(BaseModel):
    info_list: List[DynamicInfo] = Field(description="需要更新的动态信息列表")
    delete_info_list: Optional[List[DeletionInfo]] = Field(default=None, description="可选的删除列表")


class Entity(BaseModel):
    name: str = Field(..., min_length=1, description="实体名称")
    entity_type: EntityType = Field(..., description="实体类型")
    life_span: Literal["长期", "短期"] = Field(description="实体在故事中的生命周期")


class CharacterCardCore(Entity):
    last_appearance: Optional[Tuple[int, int]] = Field(default=None, description="最后出现时间：[卷号, 章节号]")
    role_type: Literal["主角", "主角团配角", "普通NPC", "反派"] = Field("主角团配角", description="角色定位")
    born_scene: str = Field(description="出场/常驻场景")
    description: str = Field(description="一句话简介与背景说明")


class CharacterCard(CharacterCardCore):
    entity_type: EntityType = Field("character", description="实体类型标记")
    personality: str = Field(description="性格关键词")
    core_drive: str = Field(description="核心驱动力/目标")
    character_arc: str = Field(description="角色在全书中的弧光")
    dynamic_info: Dict[DynamicInfoType, List[DynamicInfoItem]] = Field(
        default_factory=dict,
        description="动态信息字典，留空，系统会自动维护",
    )

    @field_validator("dynamic_info", mode="before")
    @classmethod
    def _normalize_dynamic_info(cls, v: Any) -> Dict[str, Any]:
        return DynamicInfo._normalize_dynamic_info_dict(v)


class SceneCard(Entity):
    entity_type: EntityType = Field("scene", description="实体类型标记")
    description: str = Field(description="场景/地图一句话简介")
    function_in_story: str = Field(description="在剧情中的作用")
    dynamic_state: List[str] = Field(default_factory=list, description="当前状态，由系统逐步补充维护")
    last_appearance: Optional[Tuple[int, int]] = Field(default=None, description="最后出现时间：[卷号, 章节号]")


class OrganizationCard(Entity):
    entity_type: EntityType = Field("organization", description="实体类型标记")
    description: str = Field(description="组织/势力阵营描述")
    influence: Optional[str] = Field(default=None, description="该组织对世界的影响范围/影响力")
    relationship: Optional[List[str]] = Field(default=None, description="与其他组织的关系")
    dynamic_state: List[str] = Field(default_factory=list, description="当前状态，由系统逐步补充维护")
    last_appearance: Optional[Tuple[int, int]] = Field(default=None, description="最后出现时间：[卷号, 章节号]")


class SceneCardMemory(Entity):
    entity_type: EntityType = Field("scene", description="scene entity type")
    life_span: Optional[Literal["长期", "短期"]] = Field(default=None, description="scene lifespan")
    description: str = Field(default="", description="scene description")
    function_in_story: str = Field(default="", description="scene function in story")
    dynamic_state: List[str] = Field(default_factory=list, description="scene dynamic state summary")


class OrganizationCardMemory(Entity):
    entity_type: EntityType = Field("organization", description="organization entity type")
    life_span: Optional[Literal["长期", "短期"]] = Field(default=None, description="organization lifespan")
    description: str = Field(default="", description="organization description")
    influence: Optional[str] = Field(default=None, description="organization influence")
    relationship: List[str] = Field(default_factory=list, description="organization relationships")
    dynamic_state: List[str] = Field(default_factory=list, description="organization dynamic state summary")


class ItemCard(Entity):
    entity_type: EntityType = Field("item", description="实体类型")
    life_span: Literal["长期", "短期"] = Field("长期", description="物品在故事中的生命周期")
    category: str = Field(
        default="",
        description="物品类别",
        json_schema_extra={"x-knowledge-source": "物品类别"},
    )
    description: str = Field(default="", description="物品的一句话简介或背景说明")
    owner_hint: Optional[str] = Field(default=None, description="当前或常见持有者")
    power_or_effect: Optional[str] = Field(default=None, description="物品能力、效果或用途")
    constraints: Optional[str] = Field(default=None, description="使用限制、代价或触发条件")
    current_state: Optional[str] = Field(default=None, description="物品当前状态")
    important_events: List[str] = Field(default_factory=list, description="与物品相关的重要事件摘要")

class ConceptCard(Entity):
    entity_type: EntityType = Field("concept", description="实体类型")
    life_span: Literal["长期", "短期"] = Field("长期", description="概念在故事中的生命周期")
    category: str = Field(
        default="",
        description="概念类别",
        json_schema_extra={"x-knowledge-source": "概念类别"},
    )
    description: str = Field(default="", description="概念简介")
    rule_definition: str = Field(default="", description="规则定义、适用方式或核心机制")
    cost: Optional[str] = Field(default=None, description="使用或掌握该概念的代价")
    counter_relations: List[str] = Field(default_factory=list, description="对立、克制或限制关系")
    mastery_hint: Optional[str] = Field(default=None, description="掌握门槛、领悟方式或常见使用者")
    known_by: List[str] = Field(default_factory=list, description="已知掌握、知晓或受影响的实体")
