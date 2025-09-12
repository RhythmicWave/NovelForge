import os
from sqlmodel import Session, select
from app.db.models import Prompt, CardType, Card
from loguru import logger
from app.api.endpoints.ai import RESPONSE_MODEL_MAP

from app.db.models import Knowledge, LLMConfig
# 项目模板
from app.db.models import ProjectTemplate, ProjectTemplateItem
from app.db.models import Project
from sqlmodel import select as _select

def _parse_prompt_file(file_path: str):
    """解析单个提示词文件，支持frontmatter元数据"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    filename = os.path.basename(file_path)
    name = os.path.splitext(filename)[0]
    description = f"AI任务提示词: {name}"
            
    return {
        "name": name,
        "description": description,
        "template": content.strip()
    }

def get_all_prompt_files():
    """从文件系统加载所有提示词"""
    prompt_dir = os.path.join(os.path.dirname(__file__), 'prompts')
    if not os.path.exists(prompt_dir):
        logger.warning(f"Prompt directory not found at {prompt_dir}. Cannot load prompts.")
        return {}

    prompt_files = {}
    for filename in os.listdir(prompt_dir):
       
        if filename.endswith(('.prompt', '.txt')):
            file_path = os.path.join(prompt_dir, filename)
            name = os.path.splitext(filename)[0]
            prompt_files[name] = _parse_prompt_file(file_path)
    return prompt_files

def init_prompts(db: Session):
    """初始化默认提示词（支持增量更新）"""
    existing_prompts = db.exec(select(Prompt)).all()
    existing_names = {p.name for p in existing_prompts}

    all_prompts_data = get_all_prompt_files()

    new_count = 0
    updated_count = 0
    prompts_to_add = []
    
    for name, prompt_data in all_prompts_data.items():
        if name in existing_names:
            existing_prompt = next(p for p in existing_prompts if p.name == name)
            existing_prompt.template = prompt_data['template']
            existing_prompt.description = prompt_data.get('description')
            existing_prompt.built_in = True
            updated_count += 1
        else:
            prompts_to_add.append(Prompt(**prompt_data, built_in=True))
            new_count += 1
    
    if prompts_to_add:
        db.add_all(prompts_to_add)

    if new_count > 0 or updated_count > 0:
        db.commit()
        logger.info(f"提示词更新完成: 新增 {new_count} 个，更新 {updated_count} 个。")
    else:
        logger.info("所有提示词已是最新状态。")




def create_default_card_types(db: Session):
    default_types = {
        "作品标签": {"editor_component": "TagsEditor", "is_singleton": True, "is_ai_enabled": False, "default_ai_context_template": None},
        "金手指": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content"},
        "一句话梗概": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content\n金手指/特殊能力: @金手指.content.special_abilities"},
        "故事大纲": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content\n金手指/特殊能力: @金手指.content.special_abilities\n故事梗概: @一句话梗概.content.one_sentence"},
        "世界观设定": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content\n金手指/特殊能力: @金手指.content.special_abilities\n故事大纲: @故事大纲.content.overview"},
        "核心蓝图": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content\n金手指/特殊能力: @金手指.content.special_abilities\n故事大纲: @故事大纲.content.overview\n世界观设定: @世界观设定.content\n组织/势力设定:@type:组织卡[previous:global].{content.name,content.description,content.influence,content.relationship}"},
        # 分卷大纲
        "分卷大纲": {"default_ai_context_template": (
            "总卷数:@核心蓝图.content.volume_count\n"
            "故事大纲:@故事大纲.content.overview\n"
            "作品标签:@作品标签.content\n"
            "世界观设定: @世界观设定.content.world_view\n"
            "组织/势力设定:@type:组织卡[previous:global].{content.name,content.description,content.influence,content.relationship}\n"
            "character_card:@type:角色卡[previous]\n"
            "scene_card:@type:场景卡[previous]\n"
            "上一卷信息: @type:分卷大纲[index=$current.volumeNumber-1].content\n"
            "接下来请你创作第 @self.content.volume_number 卷的细纲\n"
        )},
        "写作指南": {
            "is_singleton": False,
            "default_ai_context_template": (
                "世界观设定: @世界观设定.content.world_view\n"
                "组织/势力设定:@type:组织卡[previous:global].{content.name,content.entity_type,content.life_span,content.description,content.influence,content.relationship}\n"
                "当前分卷主线:@parent.content.main_target\n"
                "当前分卷辅线:@parent.content.branch_line\n"
                "该卷的阶段数量及卷末实体状态快照:@parent.{content.stage_count,content.entity_snapshot}\n"
                "角色卡信息:@type:角色卡[previous]\n"
                "地图/场景卡信息:@type:场景卡[previous]\n"
                "请为第 @self.content.volume_number 卷生成一份写作指南。"
            )
        },
        "阶段大纲": {"default_ai_context_template": (
            "世界观设定: @世界观设定.content.world_view\n"
            "组织/势力设定:@type:组织卡[previous:global].{content.name,content.entity_type,content.life_span,content.description,content.influence,content.relationship}\n"
            "分卷主线:@parent.content.main_target\n"
            "分卷辅线:@parent.content.branch_line\n"
            "角色卡信息:@type:角色卡[previous:global].{content.name,content.life_span,content.role_type,content.born_scene,content.description,content.personality,content.core_drive,content.character_arc}\n"
            "地图/场景卡信息:@type:场景卡[previous]\n"
            "该卷的角色行动简述:@parent.content.character_action_list\n"
            "之前的阶段故事大纲，确保章节范围、剧情能够衔接:@type:阶段大纲[previous:global:1].{content.stage_name,content.reference_chapter,content.analysis,content.overview,content.entity_snapshot}\n"
            "上一章节大纲概述，确保能够衔接剧情:@type:章节大纲[previous:global:1].{content.overview}\n"
            "注意，请务必在@parent.content.stage_count 个阶段内将故事按分卷主线收束，并达到卷末实体快照状态:@parent.content.entity_snapshot\n"
            "该卷的写作注意事项:@type:写作指南[sibling].content.content \n"
            "接下来请你创作第 @self.content.stage_number 阶段的故事细纲。"
        )},
        # 章节大纲：使用未包装模型 ChapterOutline
        "章节大纲": {"default_ai_context_template": (
            "word_view: @世界观设定.content\n"
            "volume_number: @self.content.volume_number\n"
            "volume_main_target: @type:分卷大纲[index=$current.volumeNumber].content.main_target\n"
            "volume_branch_line: @type:分卷大纲[index=$current.volumeNumber].content.branch_line\n"
            "本卷的实体action列表: @parent.content.entity_action_list\n"
            "当前阶段故事概述: @stage:current.overview\n"
            "当前阶段覆盖章节范围: @stage:current.reference_chapter\n"
            "之前的章节大纲: @type:章节大纲[sibling].{content.chapter_number,content.overview}\n"
            "请开始创作第 @self.content.chapter_number 章的大纲，保证连贯性"
        )},
        "章节正文": {"editor_component": "ChapterStudio", "is_ai_enabled": False, "default_ai_context_template": (
            "世界观设定: @世界观设定.content\n"
            "组织/势力设定:@type:组织卡[index=filter:content.name in $self.content.entity_list].{content.name,content.description,content.influence,content.relationship}\n"
            "场景卡:@type:场景卡[index=filter:content.name in $self.content.entity_list].{content.name,content.description}\n"
            "当前故事阶段大纲: @parent.content.overview\n"
            "角色卡:@type:角色卡[index=filter:content.name in $self.content.entity_list].{content.name,content.role_type,content.born_scene,content.description,content.personality,content.core_drive,content.character_arc,content.dynamic_info}\n"
            # "之前的章节大纲概述:@type:章节大纲[index=filter:content.volume_number = $self.content.volume_number && content.chapter_number < $self.content.chapter_number].{content.chapter_number,content.overview}\n"
            "最近的章节原文，确保能够衔接剧情:@type:章节正文[previous:1].{content.title,content.chapter_number,content.content}\n"
            "参与者实体列表，确保生成内容只会出场这些实体:@self.content.entity_list\n"
            "请根据第@self.content.chapter_number 章 @self.content.title 的大纲@type:章节大纲[index=filter:content.title = $self.content.title].{content.overview} 来创作章节正文内容，可以适当发散、设计与大纲内容不冲突的剧情来进行扩充，使得最终生成的内容字数3000字达到左右\n"
            "注意，写作时必须保证结尾剧情与下一章的剧情大纲不会冲突，且不会提取设计下一章剧情(如果存在的话):@type:章节大纲[index=filter:content.volume_number = $self.content.volume_number && content.chapter_number = $self.content.chapter_number+1].{content.title,content.overview}\n"
            "写作时请结合写作指南要求:@type:写作指南[index=filter:content.volume_number = $self.content.volume_number].{content.content}\n"
            )},
        "角色卡": {"default_ai_context_template": None},
        "场景卡": {"default_ai_context_template": None},
        "组织卡": {"default_ai_context_template": None},
    }

    # 类型默认 AI 参数预设（不包含 llm_config_id）
    DEFAULT_AI_PARAMS = {
        "金手指": {"prompt_name": "金手指生成", "temperature": 0.6, "max_tokens": 4096, "timeout": 60},
        "一句话梗概": {"prompt_name": "一句话梗概", "temperature": 0.6, "max_tokens": 4096, "timeout": 60},
        "故事大纲": {"prompt_name": "一段话大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 90},
        "世界观设定": {"prompt_name": "世界观设定", "temperature": 0.7, "max_tokens": 1500, "timeout": 90},
        "核心蓝图": {"prompt_name": "核心蓝图", "temperature": 0.7, "max_tokens": 8192  , "timeout": 120},
        "分卷大纲": {"prompt_name": "分卷大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "写作指南": {"prompt_name": "写作指南", "temperature": 0.6, "max_tokens": 8192, "timeout": 90},
        "阶段大纲": {"prompt_name": "阶段大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "章节大纲": {"prompt_name": "章节大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 90},
        "章节正文": {"prompt_name": "内容生成", "temperature": 0.7, "max_tokens": 8192, "timeout": 90},
        "角色卡": {"prompt_name": "角色动态信息提取", "temperature": 0.6, "max_tokens": 4096, "timeout": 60},
        "场景卡": {"prompt_name": "内容生成", "temperature": 0.6, "max_tokens": 4096, "timeout": 60},
        "组织卡": {"prompt_name": "关系提取", "temperature": 0.6, "max_tokens": 4096, "timeout": 60},
    }

    # 类型名称到内置响应模型的映射（直接用于生成 json_schema）
    TYPE_TO_MODEL_KEY = {
        "作品标签": "Tags",
        "金手指": "SpecialAbilityResponse",
        "一句话梗概": "OneSentence",
        "故事大纲": "ParagraphOverview",
        "世界观设定": "WorldBuilding",
        "核心蓝图": "Blueprint",
        "分卷大纲": "VolumeOutline",
        "写作指南": "WritingGuide",
        "阶段大纲": "StageLine",
        "章节大纲": "ChapterOutline",
        "章节正文": "Chapter",
        "角色卡": "CharacterCard",
        "场景卡": "SceneCard",
        "组织卡": "OrganizationCard",
    }

    existing_types = db.exec(select(CardType)).all()
    existing_type_names = {ct.name for ct in existing_types}

    # 默认 llm_config_id：取第一个可用 LLM 配置（若存在）
    default_llm = db.exec(select(LLMConfig)).first()

    for name, details in default_types.items():
        if name not in existing_type_names:
            # 直接在卡片类型上存储结构（json_schema）
            schema = None
            try:
                model_class = RESPONSE_MODEL_MAP.get(TYPE_TO_MODEL_KEY.get(name))
                if model_class:
                    schema = model_class.model_json_schema(ref_template="#/$defs/{model}")
            except Exception:
                schema = None
            # AI 参数预设（llm_config_id 由前端选择，不在此指定）
            ai_params = DEFAULT_AI_PARAMS.get(name)
            if ai_params is not None:
                # 若存在可用的默认 LLM，则写入其 ID；避免写 0 导致前端无法识别
                ai_params = { **ai_params, "llm_config_id": (default_llm.id if default_llm else None) }
            card_type = CardType(
                name=name,
                model_name=TYPE_TO_MODEL_KEY.get(name, name),
                description=details.get("description", f"{name}的默认卡片类型"),
                json_schema=schema,
                ai_params=ai_params,
                editor_component=details.get("editor_component"),
                is_ai_enabled=details.get("is_ai_enabled", True),
                is_singleton=details.get("is_singleton", False),
                default_ai_context_template=details.get("default_ai_context_template"),
                built_in=True,
            )
            db.add(card_type)
            logger.info(f"Created default card type: {name}")
        else:
            # 增量更新：刷新类型结构与元信息
            ct = next(ct for ct in existing_types if ct.name == name)
            try:
                model_class = RESPONSE_MODEL_MAP.get(TYPE_TO_MODEL_KEY.get(name))
                if model_class:
                    schema = model_class.model_json_schema(ref_template="#/$defs/{model}")
                    ct.json_schema = schema
            except Exception:
                pass
            # 若缺失 ai_params 则按预设填充（不覆盖用户已设置的）
            if getattr(ct, 'ai_params', None) is None:
                preset = DEFAULT_AI_PARAMS.get(name)
                if preset is not None:
                    ct.ai_params = { **preset, "llm_config_id": (default_llm.id if default_llm else None) }
            # 若缺失 model_name 则按映射补齐
            if not getattr(ct, 'model_name', None):
                ct.model_name = TYPE_TO_MODEL_KEY.get(name, name)
            ct.editor_component = details.get("editor_component")
            ct.is_ai_enabled = details.get("is_ai_enabled", True)
            ct.is_singleton = details.get("is_singleton", False)
            ct.description = details.get("description", f"{name}的默认卡片类型")
            ct.default_ai_context_template = details.get("default_ai_context_template")
            ct.built_in = True

    db.commit()
    logger.info("Default card types committed.")

# 初始化知识库（从 bootstrap/knowledge 目录导入 *.txt）
def init_knowledge(db: Session):
    knowledge_dir = os.path.join(os.path.dirname(__file__), 'knowledge')
    if not os.path.exists(knowledge_dir):
        logger.warning(f"Knowledge directory not found at {knowledge_dir}. Cannot load knowledge base.")
        return

    existing = {k.name: k for k in db.exec(select(Knowledge)).all()}
    created = 0
    updated = 0

    for filename in os.listdir(knowledge_dir):
        if not filename.lower().endswith(('.txt', '.md')):
            continue
        file_path = os.path.join(knowledge_dir, filename)
        name = os.path.splitext(filename)[0]
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
        except Exception as e:
            logger.warning(f"读取知识库文件失败 {file_path}: {e}")
            continue
        description = f"预置知识库：{name}"
        if name in existing:
            kb = existing[name]
            kb.content = content
            kb.description = description
            kb.built_in = True
            updated += 1
        else:
            db.add(Knowledge(name=name, description=description, content=content, built_in=True))
            created += 1

    if created or updated:
        db.commit()
        logger.info(f"知识库初始化完成：新增 {created}，更新 {updated}")
    else:
        logger.info("知识库已是最新状态。")


def init_project_templates(db: Session):
    """初始化系统预设项目模板（基于原有的默认卡片集合与顺序）。"""
    DEFAULT_TEMPLATE_NAME = "雪花创作法"
    # 需要这些卡片类型的 ID
    type_names_in_order = [
        ("作品标签", 0),
        ("金手指", 1),
        ("一句话梗概", 2),
        ("故事大纲", 3),
        ("世界观设定", 4),
        ("核心蓝图", 5),
    ]

    # 确保卡片类型已存在
    ct_map = {}
    for name, order in type_names_in_order:
        ct = db.exec(select(CardType).where(CardType.name == name)).first()
        if not ct:
            logger.warning(f"初始化项目模板时缺少卡片类型：{name}")
            return
        ct_map[name] = ct

    existing = db.exec(select(ProjectTemplate).where(ProjectTemplate.name == DEFAULT_TEMPLATE_NAME)).first()
    if not existing:
        tpl = ProjectTemplate(name=DEFAULT_TEMPLATE_NAME, description="系统预设模板：按雪花法创建基础卡片", built_in=True)
        db.add(tpl)
        db.flush()
        for name, order in type_names_in_order:
            db.add(ProjectTemplateItem(
                template_id=tpl.id,
                card_type_id=ct_map[name].id,
                display_order=order,
                title_override=name
            ))
        db.commit()
        logger.info("系统预设项目模板已创建")
    else:
        # 增量更新条目（以顺序为准）
        # 先删除旧项后重建，保持简单
        items = db.exec(select(ProjectTemplateItem).where(ProjectTemplateItem.template_id == existing.id)).all()
        for it in items:
            db.delete(it)
        db.flush()
        for name, order in type_names_in_order:
            db.add(ProjectTemplateItem(
                template_id=existing.id,
                card_type_id=ct_map[name].id,
                display_order=order,
                title_override=name
            ))
        existing.built_in = True
        db.add(existing)
        db.commit()
        logger.info("系统预设项目模板已更新")

# 初始化保留项目（__free__）
def init_reserved_project(db: Session):
    """确保存在一个保留项目，用于跨项目的自由卡片归档。"""
    FREE_NAME = "__free__"
    exists = db.exec(_select(Project).where(Project.name == FREE_NAME)).first()
    if not exists:
        p = Project(name=FREE_NAME, description="系统保留项目：存放自由卡片")
        db.add(p)
        db.commit()
        db.refresh(p)
        logger.info(f"已创建保留项目: {FREE_NAME} (id={p.id})")
    else:
        # 可在此处做增量更新（如描述字段）
        pass
