from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional, List, Tuple, Any

# --- Schemas for Tags ---

class Tags(BaseModel):
    """
    统一的标签模型，严格参考 primitive_models/Step1Model.py 中的 Tags 定义。
    """
    theme: str = Field(default="", description="主题类别，格式: 大类-子类")
    story_tags: List[Tuple[str, float]] = Field(default=[], description="小说类别标签,每个标签带有权重(0.4-1.0)")
    affection: str = Field(default="", description="情感关系标签")

# Replicating SpecialAbility from primitive_models/Step1Model.py for independence
class SpecialAbility(BaseModel):
    name: str = Field(description="金手指的名称")
    description: str = Field(description="金手指的具体描述")

# --- Schemas based on Task0, Task1, Task2 from tasks.py ---


class Task0Response(BaseModel):
    """Task0: 根据tags设计金手指的请求模型"""
    special_abilities_thinking: str = Field(description="从标签到金手指的创作思考过程")
    special_abilities: Optional[List[SpecialAbility]] = Field(None, description="主要金手指信息")


class Task1Response(BaseModel):
    """Task1: 根据tags、金手指设计一句话概述的请求模型"""
    one_sentence_thinking: str = Field(description="从标签/金手指到一句话概述的创作思考过程")
    one_sentence: str = Field(description="一句话概述整本小说内容")


class Task2Response(BaseModel):
    """Task2: 根据一句话概述等信息扩充为一段话概述的请求模型"""
    overview_thinking: str = Field(description="从一句话概述到一段话大纲的创作思考过程")
    overview: str = Field(description="扩展后的小说大纲")
    
class CoreIdeaResponse(Task0Response, Task1Response, Task2Response):
    """Combined response model for the entire core idea step."""
    pass

# --- Simplified AI Request Model ---

class SimpleAIRequest(BaseModel):
    """简化的AI请求模型，直接传递字符串输入"""
    input_text: str = Field(description="按照训练数据格式构造的字符串输入")
    llm_config_id: Optional[int] = Field(default=1, description="LLM配置ID")
    prompt_name: Optional[str] = Field(description="提示词名称，如不指定则使用task名称")
    response_model_name: Optional[str] = Field(description="响应模型名称")


class PowerCamp(BaseModel):
    name: str
    description: str = Field(description="该势力阵营的信息描述")
    influence: str = Field(description="该势力对小说世界的影响")

class SocialSystem(BaseModel):
    power_structure: str = Field(description="权力架构（如：封建王朝/资本联邦）")
    currency_system: List[str] = Field(default=["金币"], description="货币体系")
    major_power_camps: List[PowerCamp] = Field(description="主要势力阵营")
    technology_level: str = Field(description="科技/文明发展水平")

class CoreSystem(BaseModel):
    system_type: str = Field(description="体系类型（力量/社会/科技/异能等）")
    name: str = Field(description="体系名称（如：斗气/资本规则/朝堂权谋）")
    levels: Optional[List[str]] = Field(None, description="等级/阶层划分（可选）")
    source: str = Field(description="能量/权力来源（如：灵气/资本/皇权）")
    limitation: str = Field(description="核心限制规则（如：天道压制/法律约束/系统规则）")

class WorldviewTemplate(BaseModel):
    """
    世界观模板，字段名和结构严格参考 primitive_models/WorldView.py
    """
    world_name: str = Field(min_length=2, description="世界名称")
    era_name: str = Field(default="现代", description="时代名称")
    narrative_theme: str = Field(description="核心叙事主题（如：逆袭/复仇/救世）")
    core_conflict: str = Field(description="世界核心矛盾（如：资源争夺/种族仇恨）")
    social_system: SocialSystem = Field(description="社会体系")
    power_systems: CoreSystem = Field(description="力量体系")

class WorldBuildingResponse(BaseModel):
    world_view_thinking: str = Field(description="世界观设计的思考过程")
    world_view: WorldviewTemplate


# === Step 3: Blueprint Schemas (from primitive_models and tasks.py) ===

class CharacterCard(BaseModel):
    """
    一个简化的角色卡片模型，仅用于创建向导。
    其字段是 primitive_models/CharacterCard.py 中完整模型的一个子集。
    保留 'Schema' 后缀以明确区分这是一个用于API和验证的、非完整的模型。
    """
    name: str = Field(description="角色姓名")
    description: str = Field(description="角色一句话简介")
    core_drive: str = Field(description="核心驱动力")
    character_arc: str = Field(description="角色弧光（人物转变）")

class SceneCard(BaseModel):
    name: str = Field(description="场景/地图名称")
    description: str = Field(description="场景/地图一句话简介")
    function_in_story: str = Field(description="在剧情中的作用")

class BlueprintResponse(BaseModel):
    volume_count: int = Field(default=3, description="小说的卷数")
    character_thinking: str = Field(description="角色设计思考过程")
    character_cards: List[CharacterCard] = Field(description="核心角色卡片列表")
    scene_thinking: str = Field(description="场景设计思考过程")
    scene_cards: List[SceneCard] = Field(description="主要场景卡片列表")


# === Step 4: Volume Outline Schemas (from primitive_models/tasks.py Task5Model) ===

class CharacterAction(BaseModel):
    """角色卡，涵盖了各种信息"""
    name: Optional[str] = Field(default="", description="角色名称")
    description: Optional[str] = Field(default="", description="以第一视角讲述该角色在这卷内的主要事迹")

class StoryLine(BaseModel):
    """故事线信息，来自 primitive_models/Step2Model.py"""
    story_type: Optional[Literal['主线', '辅线']] = Field(default='主线', description="故事线类型")
    name: Optional[str] = Field(default="", description="用一个简单的名称表示该线")
    overview: Optional[str] = Field(default="", description="故事线内容概述，需要详略得当，涉及到的所有场景、角色等元素都应在这个概述中体现到。")

class StageLine(BaseModel):
    """故事按阶段划分的信息，来自 primitive_models/Step2Model.py"""
    stage_name: Optional[str] = Field(default="", description="用一个名称简单概述这个阶段")
    reference_chapter: Optional[Tuple[int, int]] = Field(default=(1, 1), description="该部分剧情的起始和结束章节号")
    overview: Optional[str] = Field(default="", description="这个阶段剧情内容概述，需要详略得当，涉及到的主要场景、角色等元素都应在这个概述中体现到。另外，若主角有了显著提升（如提升了主角多少实力或地位、增长了主角多少财富或资源之类的），则相关信息需要准确数据描述，不能省略")
    analysis: Optional[str] = Field(default="", description="以一个经验丰富的网文写手代入作者第一人称视角,'我'是如何思考设置这部分的剧情的,该部分剧情需要起到什么作用?是否设计爽点?")

class VolumeOutline(BaseModel):
    """
    分卷大纲的核心数据模型，严格参考 primitive_models/tasks.py 中的 Task5Model。
    """
    volume_number: Optional[int] = Field(default=1, description="第几卷")
    thinking: Optional[str] = Field(default="", description="根据提供的世界观、人物、地图/副本,思考本卷要如何展开,需要设计什么主线/辅线?如何推动剧情发展?")
    main_target: Optional[StoryLine] = Field(default=None, description="根据thinking设计主线目标,要让主角发展到什么地步?需描述准确数据")
    branch_line: Optional[List[StoryLine]] = Field(default=[], description="该卷的辅线或支线,包含1~3条核心辅线")
    character_thinking: Optional[str] = Field(default="", description="结合overview、提供的角色信息,如性格、核心驱动力、角色弧光等,思考在该卷要驱动角色们做什么事?要让哪些角色出场?是否要引入辅助角色?")
    new_character_cards: Optional[List[CharacterCard]] = Field(default=None, description="如果在角色行动列表中引入了新的角色，则在此处补充其信息")
    stage_lines: Optional[List[StageLine]] = Field(default=[], description="设计该卷的详细故事脉络，按阶段来划分，注意切分故事阶段时详略得当，每个阶段章节跨度不要太大,最好不超过40章")
    character_action_list: Optional[List[CharacterAction]] = Field(default=[], description="根据character_thinking,仅描述本卷要出场的角色信息")
    character_snapshot: Optional[List[str]] = Field(default=[], description="本卷结束时,主要角色(主角、重要配角,忽略次要角色)的快照状态信息")


class VolumeOutlineResponse(BaseModel):
    """Response model for volume outline generation."""
    volume_outline: VolumeOutline

# === Step 5: Chapter Outline Schemas (from primitive_models/ReverseStep1Model.py) ===

class ChapterPoint(BaseModel):
    """剧情点"""
    description: Optional[str] = Field(default="", description="剧情点描述")
    effect: Optional[str] = Field(default="", description="剧情点的作用，如推动情节发展、揭示人物性格、引出冲突、解决阻碍、引导读者、承上启下、铺垫、交代角色背景、爽点、营造紧张/绝望/不安或其他各种氛围等；")
    emotion: Optional[Literal["↗", "→", "↘", "?", "!", "！", "？"]] = Field(default="→", description="表示该剧情点的情绪曲线，↗(如热血、爽快、解气、装逼等)、→(平淡情绪)、↘(如压抑、憋屈、难受等)、?(疑惑、不解情绪)、!(震惊、期待情绪)")

class Enemy(BaseModel):
    """短期敌人"""
    chapter_number: Optional[int] = Field(default=1, description="章节号")
    name: Optional[str] = Field(default="", description="精简的名称,无需任何修饰词")
    description: Optional[str] = Field(default="", description="描述信息，背景如何，为什么是敌人？")

class ResolveEnemy(BaseModel):
    """解决短期敌人"""
    chapter_number: Optional[int] = Field(default=1, description="当前的章节号")
    resolve_id: Optional[int] = Field(default=1, description="敌人出现的chapter_number,必须小于等于当前的章节号")
    resolve_name: Optional[str] = Field(default="", description="对应的敌人名称")
    description: Optional[str] = Field(default="", description="概述如何完成该目标的，包括细节")

class ChapterOutline(BaseModel):
    """章节大纲"""
    volume_number: Optional[int] = Field(default=0, description="卷号，如果没有找到，则设置为0")
    title: Optional[str] = Field(default="", description="章节标题")
    chapter_number: Optional[int] = Field(default=1, description="章节序号")
    character_list: Optional[List[str]] = Field(default=[], description="章节中出场的重要人物列表")
    overview: Optional[str] = Field(default="", description="章节主要内容概述,详略得当。如果主角有了显著的提升，则相关信息不能省略，需要准确数据描述出来(如实力大幅提升、经济或资源大幅增长了多少)(注意，章节概述语言自然，不要用'本章如何如何'这种口吻来叙述)")
    enemy: Optional[Enemy] = Field(default=None, description="在该章是否确立了需要打败的敌人的目标")
    chapter_points: Optional[List[ChapterPoint]] = Field(default=[], description="章节中提取出的剧情点列表")
    character_level_and_wealth_changes: Optional[List[str]] = Field(default=[], description="该章节中主要角色是否变化,例如等级、境界、战力、修为等提升,或者增长了财富、功法、秘籍等。需引用准确数据,并给出提升后角色状态")
    resolve_enemy: Optional[ResolveEnemy] = Field(default=None, description="是否解决已经存在的enemy")


class ChapterOutlineResponse(BaseModel):
    """Response model for chapter outline generation."""
    chapter_outline: ChapterOutline 


# === Step 6: Batch Chapter Outline Schemas (from primitive_models/tasks.py Task6Model) ===

class SmallChapter(BaseModel):
    """
    章节的简要大纲信息，严格参考 primitive_models/tasks.py 中的 SmallChapter 定义。
    """
    title:str=Field(description="章节标题")
    chapter_number:int=Field(description="章节序号")
    overview:str=Field(description="章节概述,详略得当")
    enemy:Optional[Enemy]=Field(default=None,description="在该章是否确立了需要打败的敌人的目标")
    resolve_enemy:Optional[ResolveEnemy]=Field(default=None,description="是否解决已经存在的enemy")


class Task6Response(BaseModel):
    """
    批量生成章节大纲的响应模型，对应于 Task6Model。
    """
    chapter_list:List[SmallChapter]=Field([],description="生成的章节简述信息列表") 