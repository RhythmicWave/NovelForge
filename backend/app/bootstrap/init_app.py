import os
from sqlmodel import Session, select
from app.db.models import Prompt, CardType, OutputModel
from loguru import logger
from app.api.endpoints.ai import RESPONSE_MODEL_MAP

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
        # Adjusted to handle both .prompt and .txt files for prompts
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
            updated_count += 1
        else:
            prompts_to_add.append(Prompt(**prompt_data))
            new_count += 1
    
    if prompts_to_add:
        db.add_all(prompts_to_add)

    if new_count > 0 or updated_count > 0:
        db.commit()
        logger.info(f"提示词更新完成: 新增 {new_count} 个，更新 {updated_count} 个。")
    else:
        logger.info("所有提示词已是最新状态。")


def init_output_models(db: Session):
    """初始化/更新内置输出模型（将内置 Pydantic 模型写入 OutputModel）。"""
    existing = {om.name: om for om in db.exec(select(OutputModel)).all()}
    updated = 0
    created = 0
    for name, model in RESPONSE_MODEL_MAP.items():
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        if '$defs' in schema:
            del schema['$defs']
        if name in existing:
            om = existing[name]
            om.json_schema = schema
            om.built_in = True
            updated += 1
        else:
            db.add(OutputModel(name=name, description=f"内置输出模型 {name}", json_schema=schema, built_in=True))
            created += 1
    if created or updated:
        db.commit()
        logger.info(f"输出模型初始化完成：新增 {created}，更新 {updated}")
    else:
        logger.info("输出模型已是最新状态。")


def create_default_card_types(db: Session):
    default_types = {
        "作品标签": {"model_name": "Tags", "output_model_name": "Tags", "editor_component": "TagsEditor", "is_singleton": True, "is_ai_enabled": False, "default_ai_context_template": None},
        "金手指": {"model_name": "Task0Response", "output_model_name": "Task0Response", "is_singleton": True, "default_ai_context_template": "tags: @作品标签.content"},
        "一句话梗概": {"model_name": "Task1Response", "output_model_name": "Task1Response", "is_singleton": True, "default_ai_context_template": "tags: @作品标签.content\nspecial_abilities: @金手指.content.special_abilities"},
        "故事大纲": {"model_name": "Task2Response", "output_model_name": "Task2Response", "is_singleton": True, "default_ai_context_template": "tags: @作品标签.content\nspecial_abilities: @金手指.content.special_abilities\none_sentence: @一句话梗概.content.one_sentence"},
        "世界观设定": {"model_name": "WorldBuildingResponse", "output_model_name": "WorldBuildingResponse", "is_singleton": True, "default_ai_context_template": "tags: @作品标签.content\nspecial_abilities: @金手指.content.special_abilities\noverview: @故事大纲.content.overview"},
        "核心蓝图": {"model_name": "BlueprintResponse", "output_model_name": "BlueprintResponse", "is_singleton": True, "default_ai_context_template": "tags: @作品标签.content\nspecial_abilities: @金手指.content.special_abilities\noverview: @故事大纲.content.overview\nword_view: @世界观设定.content"},
        # 分卷大纲默认上下文：引用核心蓝图、上一卷与当前卷（若存在）
        "分卷大纲": {"model_name": "VolumeOutlineResponse", "output_model_name": "VolumeOutlineResponse", "default_ai_context_template": (
            "blueprint: @核心蓝图.content\n"
            "previous_volume: @type:分卷大纲[index=$current.volumeNumber-1].content\n"
            "current_volume: @self.content\n"
        )},
        # 章节大纲默认上下文：参考 task6 所需输入
        "章节大纲": {"model_name": "ChapterOutlineResponse", "output_model_name": "ChapterOutlineResponse", "default_ai_context_template": (
            "blueprint: @核心蓝图.content\n"
            "word_view: @世界观设定.content\n"
            "volume_number: @self.content.chapter_outline.volume_number\n"
            "volume_main_target: @type:分卷大纲[index=$current.volumeNumber].content.volume_outline.main_target\n"
            "volume_branch_line: @type:分卷大纲[index=$current.volumeNumber].content.volume_outline.branch_line\n"
            "volume_character_cards: @type:分卷大纲[index=$current.volumeNumber].content.volume_outline.character_action_list\n"
            "stage_current: @stage:current\n"
            "stage_analysis: @stage:current.analysis\n"
            "stage_overview: @stage:current.overview\n"
            "stage_reference_chapter: @stage:current.reference_chapter\n"
            "previous_chapters: @chapters:previous\n"
        )},
        "章节正文": {"model_name": "Chapter", "output_model_name": "ChapterOutline", "editor_component": "NovelEditor", "is_ai_enabled": False, "default_ai_context_template": None},
        "角色卡": {"model_name": "CharacterCard", "output_model_name": "CharacterCard", "default_ai_context_template": None},
        "场景卡": {"model_name": "SceneCard", "output_model_name": "SceneCard", "default_ai_context_template": None},
    }

    existing_types = db.exec(select(CardType)).all()
    existing_type_names = {ct.name for ct in existing_types}

    for name, details in default_types.items():
        if name not in existing_type_names:
            card_type = CardType(
                name=name,
                description=details.get("description", f"{name}的默认卡片类型"),
                model_name=details.get("model_name"),
                output_model_name=details.get("output_model_name"),
                editor_component=details.get("editor_component"),
                is_ai_enabled=details.get("is_ai_enabled", True),
                is_singleton=details.get("is_singleton", False),
                default_ai_context_template=details.get("default_ai_context_template")
            )
            db.add(card_type)
            logger.info(f"Created default card type: {name}")
        else:
            # 增量更新（同步 output_model_name 等）
            ct = next(ct for ct in existing_types if ct.name == name)
            ct.model_name = details.get("model_name")
            ct.output_model_name = details.get("output_model_name")
            ct.editor_component = details.get("editor_component")
            ct.is_ai_enabled = details.get("is_ai_enabled", True)
            ct.is_singleton = details.get("is_singleton", False)
            ct.description = details.get("description", f"{name}的默认卡片类型")
            ct.default_ai_context_template = details.get("default_ai_context_template")

    db.commit()
    logger.info("Default card types committed.")