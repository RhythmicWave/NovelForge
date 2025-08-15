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
    special_abilities_thinking: str = Field(description="从标签到金手指的创作思考过程。",examples=["示例输出，仅供学习思考方式，不要被具体内容影响：根据标签“重生”和“无敌流”，我需要设计一个让主角能够不断尝试、不断变强，最终达到无敌状态的金手指。仅仅重生一次不足以支撑“无敌流”的长期发展，因此，将“重生”特性深化为“无限复活并回溯时间”的能力，每次复活都能保留经验和记忆，这既符合“重生”的特点，又能为主角的“无敌”之路提供逻辑支撑。同时，结合“异世大陆”和“文明推演”的背景，这种能力能够让主角在面对未知世界时，通过反复试错来积累知识和经验，从而实现降维打击，迅速崛起。这个金手指的设定，能够让读者对主角如何利用这种能力解决困境、颠覆旧秩序产生强烈的期待感。"])
    special_abilities: Optional[List[SpecialAbility]] = Field(None, description="主要金手指信息。金手指可以是各种系统、模拟器等这种具体的，也可以是某种优势/天赋/体质等，例如主角重生或者穿越，那么ta的先知先觉也是一种金手指。")


class Task1Response(BaseModel):
    """Task1: 根据tags、金手指设计一句话概述的请求模型"""
    one_sentence_thinking: str = Field(description="从标签/金手指到一句话概述的创作思考过程。",examples=["示例输出，仅供学习思考方式，不要被具体内容影响：考虑到'玄幻奇幻-异世大陆'的主题和'穿越'、'异界科学流'等标签，我首先需要构建一个跨世界的故事框架。现代剑道高手与异世界魔法师的相遇是个很好的切入点，'禁忌魔法传送门'金手指为这一相遇提供了合理契机。同时，'单CP'的情感标签要求这段关系要成为故事的重要线索。'文明碰撞'和'异界科学流'标签则提示要让主角带来现代世界的知识优势，形成独特的冲突和看点。综合这些元素，我决定构建一个关于现代人进入魔法世界，通过知识优势与个人成长影响整个异界命运的故事。"])
    one_sentence: str = Field(description="一句话概述整本小说内容")


class Task2Response(BaseModel):
    """Task2: 根据一句话概述等信息扩充为一段话概述的请求模型"""
    overview_thinking: str = Field(description="从一句话概述到一段话大纲的创作思考过程。",examples=["示例输出，仅供学习思考方式，不要被具体内容影响：基于一句话概述，进一步思考故事的具体展开。从'穿越'标签出发，需要交代主角穿越后的身份转变和初始困境。'反派流'和'幕后流'决定了主角必须采取非传统的反派手段。'种田流'提示要详细描写魔族社会发展过程。'傲慢天赋'金手指则提供了主角解决问题的独特方式。整个故事需要展现出主角如何利用现代思维和智谋，在有限时间内完成魔族改造和人类世界的和平渗透。"])
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
    civilization_level: Optional[str] = Field(description="科技/文明发展水平")

class CoreSystem(BaseModel):
    system_type: str = Field(description="体系类型（力量/社会/科技/异能等）")
    name: str = Field(description="体系名称（如：斗气/资本规则/朝堂权谋）")
    levels: Optional[List[str]] = Field(None, description="等级/阶层划分（可选）")
    source: str = Field(description="能量/权力来源（如：灵气/资本/皇权）")

class WorldviewTemplate(BaseModel):
    """
    世界观模板，字段名和结构严格参考 primitive_models/WorldView.py
    """
    world_name: str = Field(min_length=2, description="世界名称")
    narrative_theme: str = Field(description="核心叙事主题（如：逆袭/复仇/救世）")
    core_conflict: str = Field(description="世界核心矛盾（如：资源争夺/种族仇恨）")
    social_system: SocialSystem = Field(description="社会体系")
    power_systems: CoreSystem = Field(description="力量体系")

class WorldBuildingResponse(BaseModel):
    world_view_thinking: str = Field(description="世界观设计的思考过程",examples=["示例输出，仅用于学习思考方式，不要被具体内容影响：在设计世界观时，我希望构建一个既贴近现实又充满科幻想象力的框架。首先，为了让读者有代入感，我选择将故事背景设定在现代都市，这样主角的特殊能力与日常生活的冲突会更具张力。但仅仅是现代都市显然不够支撑“时空穿越”的主题，因此，我引入了“梦境”作为连接现实与未来的桥梁。这个梦境世界，最初是现实的映射，但随着主角的干预，它会发生剧烈变化，甚至出现“旧海”和“新海市”这种未来世界的差异，这为世界观增添了层次感和探索空间。为了解释这种变化，我需要一套严谨的时空法则，比如“时空蝴蝶效应”、“历史线修正”等，这些法则不仅解释了梦境与现实的互动，也为剧情的推进和冲突的产生提供了逻辑基础。同时，为了承载“文明推演”和“异界科学流”的标签，我构思了一个隐藏在幕后的组织，他们掌握着超越时代的科技和对时空法则的深刻理解，他们的存在是世界核心矛盾的体现——即关于历史走向的掌控权。社会体系上，现实世界是现代社会，而未来梦境则可能呈现出科技高度发达但社会畸形（如积分至上）或末日废土（如辐射灾害）的多种面貌，这种对比能增强故事的深度和警示意义。核心驱动体系上，除了主角的梦境能力，还需要有“超时空粒子”等科学概念作为力量来源和理论支撑，使得整个世界观在科幻的框架下显得自洽且充满探索潜力。"])
    world_view: WorldviewTemplate


# === Step 3: Blueprint Schemas (from primitive_models and tasks.py) ===

from .entity import CharacterCard as CharacterCard  # 以完整角色卡替换简化模型
from .entity import SceneCard as SceneCard

class EntityInvolved(BaseModel):
    name:str=Field(description="实体名称")
    desc:Optional[str]=Field(None,description="实体描述")

class BlueprintResponse(BaseModel):
    volume_count: int = Field(default=3, description="小说的卷数")
    character_thinking: str = Field(description="角色设计思考过程",examples=["示例输出，仅供学习思考方式，不要被具体内容影响：在设计角色时，我秉持着“多样性与互补性”的原则，确保每个核心角色都能在故事中发挥独特的作用，并与主角团形成紧密的联系。\n\n首先是主角王小明。他作为“穿越者”，必须具备现代人的思维和适应能力。我设定他是一名剑道高手，这既能让他快速融入异世界，又能与异世界的“剑术”体系相呼应。他的核心驱动力是“高额酬金”和“守护海雯”，这让他从一个旁观者逐渐转变为异世界的参与者和守护者。他的成长弧光将是“从现实世界的普通人到异世界的救世主”，这与“进化流”的标签紧密相连。\n\n女主角海雯是故事的引路人。她必须是异世界的核心人物，拥有强大的魔法天赋和独特的背景。我设定她是“天才魔法师”和“王族联姻的逃犯”，这为她提供了最初的困境和行动动机。她与主角的“闪婚”设定，迅速确立了他们的CP关系，也为后续的情感发展奠定了基础。她的核心驱动力是“逃避联姻”和“拯救世界”，这让她在个人命运与世界命运之间找到了平衡点。她的角色弧光是“从逃亡者到拯救世界的王宫魔法师”，展现了她的成长与担当。\n\n希斯作为主要反派，必须强大且神秘。我设定她是“海雯的姑姑”和“邪恶魔法师”，这种亲缘关系增加了故事的复杂性和情感张力。她的核心动机是“毁灭世界”，这与失落文明的诅咒紧密相关。她的角色弧光是“从天才魔法师到毁灭者，最终选择离开”，为故事的结局增添了悲剧色彩。\n\n林晓雪则作为连接现实世界的桥梁，她的“学霸”设定让她能够为异世界提供现代知识，体现“异界科学流”和“文明碰撞”的标签。\n\n通过这些角色的设计，我希望构建一个充满张力、情感丰富、并能共同推动宏大叙事的角色群像。"])
    character_cards: List[CharacterCard] = Field(description="核心角色卡片列表，仅在此生成长期的核心角色")
    scene_thinking: str = Field(description="场景设计思考过程",examples=["示例输出，仅供学习思考方式，不要被具体内容影响：在设计地图和场景时，我遵循了从局部到全局、从已知到未知、层层递进的原则，以确保故事的节奏感和世界观的逐步展开。我的核心思路是：每个场景不仅是故事发生的地点，更是推动剧情、展现角色成长、揭示世界观秘密的关键。\n\n**第一卷：初入异世与初步探索**\n我首先设置了蓝星（现实世界）作为故事的起点和主角的“已知世界”，这让读者有代入感。然后通过“墨兰塔”和“兰特王国(明月城)”引入异世界的核心地域，这里是魔法与剑并存的典型场景，也是初期冲突的爆发点。墨兰塔作为魔法师的圣地，既是海雯的背景，也为主角学习魔法提供了场所。明月城则代表了异世界的政治中心和战争前线。这些场景的作用是让主角初步适应异世界，展现其适应能力和初步实力提升，并引出主要势力。\n\n**第二卷：势力发展与联盟建立**\n随着剧情发展，我需要更广阔的舞台来展现主角团的势力扩张和宏大计划。因此，引入“兰特王国（惊鸿之城）”作为新的盟友基地，这里将成为公主复国和建立同盟的战略中心。同时，为了展现战争的全面性，我设计了“高栏联邦（临崖城/中部哨塔/日出山）”作为重要的战场和政治博弈地，通过这里的冲突来推动联盟的形成。解放“明月城”则是这一卷的高潮，标志着复国计划的关键一步。这些场景的作用是让主角团从被动应战转变为主动出击，展现其战略眼光和领导力，并促成同盟的建立。\n\n**第三卷：统一战争与古老秘密的揭示**\n进入第三卷，故事重心转向统一异世界大陆和揭示更深层次的秘密。因此，我将场景扩展到“日月国”和“圣瓦伦帝国（特西斯丁堡）”。日月国是联军推进的必经之地，通过这里的战役展现主角团的强大力量。圣瓦伦帝国首都“特西斯丁堡”是最终决战的地点，它的陷落标志着旧秩序的终结。这些场景的作用是完成统一大业，同时揭示世界观的深层秘密，为最终的危机埋下伏笔。\n\n**第四卷：末日危机与最终抉择**\n最后一卷，世界面临毁灭，场景设计围绕“拯救”和“终结”展开。“临崖城”和“惊鸿之城”再次出现，但这次它们承载的是收集王族之血和科技求生的希望。最终的“起源之地/燃烧的山巅”是决战的舞台，这里是诅咒的源头，也是解咒的关键。这些场景的作用是集中所有线索，完成最终的救赎，并让主角团做出关于归属的最终选择，为整个故事画上句号。"])
    scene_cards: List[SceneCard] = Field(description="主要场景卡片列表，仅在此生成长期的核心地图/场景")


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
    分卷大纲的核心数据模型
    """
    volume_number: Optional[int] = Field(default=1, description="第几卷")
    thinking: Optional[str] = Field(default="", description="根据提供的世界观、人物、地图/副本,思考本卷要如何展开,需要设计什么主线/辅线?如何推动剧情发展?",examples=["示例输出，仅供学习思考方式，不要被具体内容影响：本卷作为开篇，我的核心思考是如何迅速确立主角“无限复活”的金手指特性，并将其与残酷的异世大陆背景相结合，制造强烈的生存压迫感，从而驱动主角从绝境中崛起。我需要设计一个循序渐进的成长路径，让主角从一个濒死之人，通过每次复活积累经验和知识，逐步适应环境，并最终在A市站稳脚跟，积累原始资本，建立初步势力。同时，为了后续的宏大叙事，我必须在这一卷中埋下世界观的伏笔，例如社会阶层的固化、更高文明的操控等，通过主角的视角逐步揭示。在人物塑造上，我将引入一群性格各异的伙伴，他们既是主角的助力，也能通过他们的视角反衬主角的强大和特殊。爽点方面，主角利用金手指的“先知”优势，在股市和冒险中实现降维打击，以及最终对早期反派的复仇，都将是重要的爽点设计。"])
    main_target: Optional[StoryLine] = Field(default=None, description="根据thinking设计主线目标,要让主角发展到什么地步?需描述准确数据")
    branch_line: Optional[List[StoryLine]] = Field(default=[], description="该卷的辅线或支线,包含1~3条核心辅线")
    character_thinking: Optional[str] = Field(default="", description="结合overview、提供的角色信息,如性格、核心驱动力、角色弧光等,思考在该卷要驱动角色们做什么事?要让哪些角色出场?是否要引入辅助角色?",examples=["示例输出，仅学习思考方式，不要被具体内容影响：在本卷中，我将重点驱动主角，让他充分利用“无限复活”的能力，从一个绝境中的幸存者，逐步成长为A市的领袖。他将通过反复试错来学习战斗技巧、社会规则，并利用信息差在股市中快速积累财富。我还需要引入孙清雨、王火、韩天等核心配角，让他们在主角的成长过程中扮演重要的辅助角色：孙清雨作为主角的第一个伙伴和忠实追随者，将见证并参与主角的早期崛起；王火则提供技术支持，并成为主角“复活”秘密的知情人；韩天则在装备改造和技术研发上提供关键帮助。这些角色的出场和互动，不仅能推动剧情发展，也能丰富主角的人设，展现他智谋超群、善于利用资源的特点。同时，林森作为本卷的主要反派，将是主角初期反抗旧秩序的具象化目标，他的存在将不断刺激主角变强和复仇。"])
    new_character_cards: Optional[List[CharacterCard]] = Field(default=None, description="如果在角色行动列表中引入了新的角色，则在此处补充其信息")
    stage_lines: Optional[List[StageLine]] = Field(default=[], description="设计该卷的详细故事脉络，按阶段来划分，注意切分故事阶段时详略得当，每个阶段章节跨度不要太大,最好不超过30章")
    character_action_list: Optional[List[CharacterAction]] = Field(default=[], description="根据character_thinking,仅描述本卷要出场的角色信息")
    character_snapshot: Optional[List[str]] = Field(default=[], description="本卷结束时,主要角色(主角、重要配角,忽略次要角色)的快照状态信息")



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
   
    character_list: Optional[List[EntityInvolved]] = Field(
        default=[],
        description="章节中出场的重要人物列表；name 必须是纯姓名（不得包含括号/备注），关于实体的备注信息写入 desc 字段",
    )
    overview: Optional[str] = Field(default="", description="章节主要内容概述,详略得当。如果主角有了显著的提升，则相关信息不能省略，需要准确数据描述出来(如实力大幅提升、经济或资源大幅增长了多少)")
    # enemy: Optional[Enemy] = Field(default=None, description="在该章是否确立了需要打败的敌人的目标")
    # chapter_points: Optional[List[ChapterPoint]] = Field(default=[], description="章节中提取出的剧情点列表")
    # character_level_and_wealth_changes: Optional[List[str]] = Field(default=[], description="该章节中主要角色是否变化,例如等级、境界、战力、修为等提升,或者增长了财富、功法、秘籍等。需引用准确数据,并给出提升后角色状态")
    # resolve_enemy: Optional[ResolveEnemy] = Field(default=None, description="是否解决已经存在的enemy")
    


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
    
class Chapter(BaseModel):
    volume_number: Optional[int] = Field(default=0, description="卷号，如果没有找到，则设置为0")
    title: Optional[str] = Field(default="", description="章节标题")
    chapter_number: Optional[int] = Field(default=1, description="章节序号")

    entity_list: Optional[List[EntityInvolved]] = Field(
        default=[],
        description="章节中参与的重要实体列表；name 必须是纯名称（不得包含括号/备注），关于实体的写作指引信息写入 desc 字段，可留空",
    )
    content:Optional[str]=Field(default="",description="章节正文内容")