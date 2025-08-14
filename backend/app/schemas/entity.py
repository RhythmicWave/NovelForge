from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union, Tuple
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class DynamicInfoType(Enum):
    """角色动态信息大类。"""
    SYSTEM_INFO = "系统/模拟器/金手指信息"
    LEVEL = "等级/修为境界"
    EQUIPMENT = "装备/法宝"
    KNOWLEDGE="知识/情报"
    ASSET = "资产/领地"
    SKILL = "功法/技能"
    BLOODLINE = "血脉/体质"
    CONNECTION = "人脉/人情"
    MENTAL_STATE = "心理想法/目标快照"
    
class DynamicInfoItem(BaseModel):
    id:int=Field(-1,description="手动设置，无需生成；并入时若为-1将自动赋值为该类别的顺序序号（从1开始）")
    info:str=Field(description="简要描述具体动态信息。")
    weight:float=Field(ge=0.0, le=1.0, description="该信息的重要性权重，范围0~1，越大越重要")
    
class DynamicInfo(BaseModel):
    name: str = Field(description="角色名称。")
    dynamic_info: Dict[DynamicInfoType, List[DynamicInfoItem]] = Field(default_factory=dict, description="动态信息字典，键为 DynamicInfoType；值为带 id/weight 的信息项列表。‘心理想法/目标快照’为必选项。")

class ModifyDynamicInfo(BaseModel):
    name:str=Field(description="角色名称。")
    dynamic_type:DynamicInfoType=Field(description="动态信息类型。")
    id:int=Field(description="要修改的动态类型信息的id")
    weight:float=Field(ge=0.0, le=1.0, description="修改后该信息的权重，范围0~1，表示重要性")

class UpdateDynamicInfo(BaseModel):
    info_list:List[DynamicInfo]=Field(description="需要更新的动态信息列表，尽量只提取足够重要的信息")
    modify_info_list: Optional[List[ModifyDynamicInfo]] = Field(default=None, description="（可选）对已有信息的权重修正列表")


class Entity(BaseModel):
    name: str = Field(..., min_length=1, description="实体姓名（唯一标识）。")
    life_span: Literal['长期','短期'] = Field("短期", description="实体在故事中的生命周期。")
    active_volumes: Optional[List[int]] = Field(default=None, description="实体活跃的卷号集合（短期实体用）。")
    # 最后出场时间（二维：卷号、章节号）
    last_appearance: Optional[Tuple[int, int]] = Field(default=None, description="最后出场时间：[卷号, 章节号]")




class CharacterCardCore(Entity):
    role_type: Literal['主角','主角团配角','普通NPC','反派'] = Field("主角团配角", description="角色定位。")
    born_scene: Optional[str] = Field(default=None, description="出场/常驻场景。")
    description: str = Field(description="一句话简介/背景与关系概述。")


class CharacterCard(CharacterCardCore):
    """完整角色卡（供前后端强类型与可视化使用）。"""
    personality: Optional[str] = Field(default=None, description="性格关键词，如'谨慎'、'幽默'。")
    core_drive: Optional[str] = Field(default=None, description="核心驱动力/目标。")
    character_arc: List[str] = Field(default_factory=list, description="角色弧光/阶段变化。")

    # 动态信息（新设计方案：集中作为真相源）
    dynamic_info: Dict[DynamicInfoType, List[DynamicInfoItem]] = Field(default_factory=dict, description="动态信息字典，键为 DynamicInfoType；值为 DynamicInfoItem[]。")

    class Config:
        use_enum_values = True  # pydantic v2：序列化枚举为值


class SceneCard(Entity):
    name: str = Field(description="场景/地图名称")
    description: str = Field(description="场景/地图一句话简介")
    function_in_story: str = Field(description="在剧情中的作用") 