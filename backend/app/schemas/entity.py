from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union, Tuple
from pydantic import BaseModel, Field, field_validator

# 以 Literal 表达可选集合，并提供常量数组供遍历/Schema 构造
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

# 实体类型标识（统一主类型）
EntityType = Literal['character', 'scene', 'organization']


class DynamicInfoItem(BaseModel):
    id:int=Field(-1,description="手动设置，无需生成；并入时若为-1将自动赋值为该类别的顺序序号（从1开始）")
    info:str=Field(description="简要描述具体动态信息。")
    # weight:float=Field(description="权重，0-1之间")
    
class DynamicInfo(BaseModel):
    name: str = Field(description="角色名称。")
    # 键直接使用中文字面量类型，前后端一致
    dynamic_info: Dict[DynamicInfoType, List[DynamicInfoItem]] = Field(default_factory=dict, description="动态信息字典，键为中文类别；值为信息项列表。")

    @field_validator('dynamic_info', mode='before')
    @classmethod
    def _normalize_keys(cls, v: Any) -> Dict[str, Any]:
        if not isinstance(v, dict):
            return {}
        normalized: Dict[str, Any] = {}
        allowed = set(DYNAMIC_INFO_TYPES)
        for k, arr in v.items():
            key = k if isinstance(k, str) else str(k)
            # 仅保留允许的中文键，其它忽略
            if key in allowed:
                normalized[key] = arr
        return normalized

class DeletionInfo(BaseModel):
    name: str = Field(description="角色名称。")
    dynamic_type: DynamicInfoType = Field(description="动态信息类型。")
    id: int = Field(gt=0, description="要删除的动态信息的ID (不能为-1)")

class UpdateDynamicInfo(BaseModel):
    info_list:List[DynamicInfo]=Field(description="需要更新的动态信息列表，尽量只提取足够重要的信息")
    delete_info_list: Optional[List[DeletionInfo]] = Field(default=None, description="（可选）为新增信息腾出空间而要删除的旧信息列表")


class Entity(BaseModel):
    name: str = Field(..., min_length=1, description="实体名称（唯一标识），不包含任何别称、外号、称号等信息，单纯的名称。")
    entity_type: EntityType = Field(..., description="实体类型标记。")
    life_span: Literal['长期','短期'] = Field(description="实体在故事中的生命周期。长期表示跨卷存在，短期表示仅在单卷内产生影响")
    # 最后出场时间（二维：卷号、章节号）
    last_appearance: Optional[Tuple[int, int]] = Field(default=None, description="最后出场时间：[卷号, 章节号]")



class CharacterCardCore(Entity):
    role_type: Literal['主角','主角团配角','普通NPC','反派'] = Field("主角团配角", description="角色定位。")
    born_scene: str = Field(description="出场/常驻场景。")
    description: str = Field(description="一句话简介/背景与关系概述。")


class CharacterCard(CharacterCardCore):
    """完整角色卡。"""
    # 固定实体类型标记
    entity_type: EntityType = Field('character', description="实体类型标记。")
    personality: str = Field(description="性格关键词，如'谨慎'、'幽默'。")
    core_drive: str = Field(description="核心驱动力/目标。")
    character_arc: str = Field(description="一段话简要描述角色在全书的弧光/阶段变化。")

    # 动态信息（新设计方案：集中作为真相源）
    dynamic_info: Dict[DynamicInfoType, List[DynamicInfoItem]] = Field(default_factory=dict, description="动态信息字典，留空，勿生成信息，系统会自动维护。")


class SceneCard(Entity):
    # 固定实体类型标记
    entity_type: EntityType = Field('scene', description="实体类型标记。")
    description: str = Field(description="场景/地图一句话简介")
    function_in_story: str = Field(description="在剧情中的作用") 

# 组织实体
class OrganizationCard(Entity):
    entity_type: EntityType = Field('organization', description="实体类型标记。")
    description: str = Field(description="该组织/势力阵营的信息描述")
    influence: Optional[str] = Field(default=None, description="该组织对小说世界的影响范围/影响力")
    relationship:Optional[List[str]]=Field(description="该组织与其他组织的关系，例如敌对、合作、中立等") 