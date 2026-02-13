"""卡片类型初始化

初始化默认卡片类型及其Schema定义。
"""

import re
from typing import Any, Dict

from sqlmodel import Session, select
from loguru import logger

from app.db.models import CardType, LLMConfig
from app.schemas.response_registry import RESPONSE_MODEL_MAP
from .registry import initializer


FIELD_TITLE_ZH_MAP: Dict[str, str] = {
    "content": "内容",
    "theme": "主题",
    "audience": "目标读者",
    "narrative_person": "叙事人称",
    "story_tags": "故事标签",
    "affection": "情感关系",
    "name": "名称",
    "description": "描述",
    "special_abilities_thinking": "金手指设计思考",
    "special_abilities": "金手指",
    "one_sentence_thinking": "一句话梗概思考",
    "one_sentence": "一句话梗概",
    "overview_thinking": "大纲扩展思考",
    "overview": "概述",
    "power_structure": "权力结构",
    "currency_system": "货币体系",
    "background": "背景",
    "major_power_camps": "主要势力阵营",
    "world_view_thinking": "世界观设计思考",
    "world_view": "世界观",
    "volume_count": "总卷数",
    "character_thinking": "角色设计思考",
    "character_cards": "角色卡",
    "scene_thinking": "场景设计思考",
    "scene_cards": "场景卡",
    "organization_thinking": "组织设计思考",
    "organization_cards": "组织卡",
    "volume_number": "卷号",
    "title": "标题",
    "main_target": "主线目标",
    "branch_line": "辅线",
    "new_character_cards": "新增角色卡",
    "new_scene_cards": "新增场景卡",
    "stage_count": "阶段数量",
    "character_action_list": "角色行动列表",
    "entity_snapshot": "实体状态快照",
    "stage_number": "阶段号",
    "chapter_number": "章节号",
    "entity_list": "实体列表",
    "stage_name": "阶段名称",
    "reference_chapter": "参考章节范围",
    "analysis": "分析",
    "chapter_outline_list": "章节大纲列表",
    "entity_type": "实体类型",
    "life_span": "生命周期",
    "role_type": "角色类型",
    "born_scene": "出生场景",
    "personality": "性格",
    "core_drive": "核心驱动力",
    "character_arc": "角色弧光",
    "influence": "影响力",
    "relationship": "关系",
    "dynamic_info": "动态信息",
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _derive_title_from_description(description: Any) -> str | None:
    if not isinstance(description, str):
        return None
    desc = description.strip()
    if not desc or not _contains_cjk(desc):
        return None

    candidate = re.split(r"[，。；;：:（(\n]", desc, maxsplit=1)[0].strip()
    if not candidate:
        return None
    if len(candidate) > 16:
        candidate = candidate[:16].strip()
    return candidate or None


def _localize_schema_titles(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                for field_name, field_schema in properties.items():
                    if not isinstance(field_schema, dict):
                        continue
                    current_title = str(field_schema.get("title") or "")
                    if not _contains_cjk(current_title):
                        localized = FIELD_TITLE_ZH_MAP.get(field_name) or _derive_title_from_description(
                            field_schema.get("description")
                        )
                        if localized:
                            field_schema["title"] = localized
                    visit(field_schema)

            defs = node.get("$defs")
            if isinstance(defs, dict):
                for def_schema in defs.values():
                    visit(def_schema)

            items = node.get("items")
            if isinstance(items, dict):
                visit(items)

            for union_key in ("anyOf", "oneOf", "allOf"):
                variants = node.get(union_key)
                if isinstance(variants, list):
                    for variant in variants:
                        visit(variant)

        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(schema)
    return schema


@initializer(name="卡片类型", order=20)
def create_default_card_types(session: Session) -> None:
    """初始化默认卡片类型
    
    创建所有内置卡片类型及其Schema、AI参数预设等。
    
    Args:
        session: 数据库会话
    """
    default_types = {
        "通用文本": {"editor_component": "MarkdownTextEditor", "is_singleton": False, "is_ai_enabled": False, "default_ai_context_template": None},
        "作品标签": {"editor_component": "TagsEditor", "is_singleton": True, "is_ai_enabled": False, "default_ai_context_template": None},
        "金手指": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content"},
        "一句话梗概": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content\n金手指/特殊能力: @金手指.content.special_abilities"},
        "故事大纲": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content\n金手指/特殊能力: @金手指.content.special_abilities\n故事梗概: @一句话梗概.content.one_sentence"},
        "世界观设定": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content\n金手指/特殊能力: @金手指.content.special_abilities\n故事大纲: @故事大纲.content.overview"},
        "核心蓝图": {"is_singleton": True, "default_ai_context_template": "作品标签: @作品标签.content\n金手指/特殊能力: @金手指.content.special_abilities\n故事大纲: @故事大纲.content.overview\n世界观设定: @世界观设定.content\n组织/势力设定:@type:组织卡[previous:global].{content.name,content.description,content.influence,content.relationship}"},
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
            "本卷的StageCount总数为：@parent.content.stage_count\n"
            "注意，请务必在@parent.content.stage_count 个阶段内将故事按分卷主线收束，并达到卷末实体快照状态:@parent.content.entity_snapshot\n"
            "该卷的写作注意事项:@type:写作指南[sibling].content.content \n"
            "接下来请你创作第 @self.content.stage_number 阶段的故事细纲。"
        )},
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
        "章节正文": {"editor_component": "CodeMirrorEditor", "is_ai_enabled": False, "default_ai_context_template": (
            "世界观设定: @世界观设定.content\n"
            "组织/势力设定:@type:组织卡[index=filter:content.name in $self.content.entity_list].{content.name,content.description,content.influence,content.relationship}\n"
            "场景卡:@type:场景卡[index=filter:content.name in $self.content.entity_list].{content.name,content.description}\n"
            "当前故事阶段大纲: @parent.content.overview\n"
            "角色卡:@type:角色卡[index=filter:content.name in $self.content.entity_list].{content.name,content.role_type,content.born_scene,content.description,content.personality,content.core_drive,content.character_arc,content.dynamic_info}\n"
            "最近的章节原文，确保能够衔接剧情:@type:章节正文[previous:1].{content.title,content.chapter_number,content.content}\n"
            "参与者实体列表，确保生成内容只会出场这些实体:@self.content.entity_list\n"
            "请根据 @self.content.chapter_number： @self.content.title 的大纲@type:章节大纲[index=filter:content.title = $self.content.title].{content.overview} 来创作章节正文内容，可以适当发散、设计与大纲内容不冲突的剧情来进行扩充，使得最终生成的内容字数3000字达到左右\n"
            "注意，写作时必须保证结尾剧情与下一章的剧情大纲不会冲突，且不会提前涉及下一章剧情(如果存在的话):@type:章节大纲[index=filter:content.volume_number = $self.content.volume_number && content.chapter_number = $self.content.chapter_number+1].{content.title,content.overview}\n"
            "写作时请结合写作指南要求:@type:写作指南[index=filter:content.volume_number = $self.content.volume_number].{content.content}\n"
            )},
        "角色卡": {"default_ai_context_template": None},
        "场景卡": {"default_ai_context_template": None},
        "组织卡": {"default_ai_context_template": None},
    }

    # 类型默认 AI 参数预设（不包含 llm_config_id）
    DEFAULT_AI_PARAMS = {
        "金手指": {"prompt_name": "金手指生成", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
        "一句话梗概": {"prompt_name": "一句话梗概", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
        "故事大纲": {"prompt_name": "一段话大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "世界观设定": {"prompt_name": "世界观设定", "temperature": 0.7, "max_tokens": 4096, "timeout": 150},
        "核心蓝图": {"prompt_name": "核心蓝图", "temperature": 0.7, "max_tokens": 8192, "timeout": 150},
        "分卷大纲": {"prompt_name": "分卷大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 150},
        "写作指南": {"prompt_name": "写作指南", "temperature": 0.6, "max_tokens": 8192, "timeout": 120},
        "阶段大纲": {"prompt_name": "阶段大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "章节大纲": {"prompt_name": "章节大纲", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "章节正文": {"prompt_name": "内容生成", "temperature": 0.7, "max_tokens": 8192, "timeout": 120},
        "角色卡": {"prompt_name": "角色动态信息提取", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
        "场景卡": {"prompt_name": "内容生成", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
        "组织卡": {"prompt_name": "关系提取", "temperature": 0.6, "max_tokens": 4096, "timeout": 120},
    }

    # 类型名称到内置响应模型的映射（直接用于生成 json_schema）
    TYPE_TO_MODEL_KEY = {
        "通用文本" : "Text",
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

    existing_types = session.exec(select(CardType)).all()
    existing_type_names = {ct.name for ct in existing_types}
    existing_type_by_name = {ct.name: ct for ct in existing_types}

    # 默认 llm_config_id：取第一个可用 LLM 配置（若存在）
    default_llm = session.exec(select(LLMConfig)).first()

    for name, details in default_types.items():
        if name not in existing_type_names:
            # 直接在卡片类型上存储结构（json_schema）
            schema = None
            try:
                model_class = RESPONSE_MODEL_MAP.get(TYPE_TO_MODEL_KEY.get(name))
                if model_class:
                    schema = model_class.model_json_schema(ref_template="#/$defs/{model}")
                    schema = _localize_schema_titles(schema)
            except Exception:
                schema = None
            # AI 参数预设（llm_config_id 由前端选择，不在此指定）
            ai_params = DEFAULT_AI_PARAMS.get(name)
            if ai_params is not None:
                # 若存在可用的默认 LLM，则写入其 ID；避免写 0 导致前端无法识别
                ai_params = {**ai_params, "llm_config_id": (default_llm.id if default_llm else None)}
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
            session.add(card_type)
            logger.info(f"Created default card type: {name}")
        else:
            # 增量更新：刷新类型结构与元信息
            ct = existing_type_by_name[name]
            try:
                model_class = RESPONSE_MODEL_MAP.get(TYPE_TO_MODEL_KEY.get(name))
                if model_class:
                    schema = model_class.model_json_schema(ref_template="#/$defs/{model}")
                    schema = _localize_schema_titles(schema)
                    ct.json_schema = schema
            except Exception:
                pass
            # 若缺失 ai_params 则按预设填充（不覆盖用户已设置的）
            if getattr(ct, 'ai_params', None) is None:
                preset = DEFAULT_AI_PARAMS.get(name)
                if preset is not None:
                    ct.ai_params = {**preset, "llm_config_id": (default_llm.id if default_llm else None)}
            # 若缺失 model_name 则按映射补齐
            if not getattr(ct, 'model_name', None):
                ct.model_name = TYPE_TO_MODEL_KEY.get(name, name)
            ct.editor_component = details.get("editor_component")
            ct.is_ai_enabled = details.get("is_ai_enabled", True)
            ct.is_singleton = details.get("is_singleton", False)
            ct.description = details.get("description", f"{name}的默认卡片类型")
            ct.default_ai_context_template = details.get("default_ai_context_template")
            ct.built_in = True

    # 自动同步：将未映射到默认卡片类型的内置响应模型写入 CardType
    # 目的：避免新增响应模型后，前端“设置-卡片类型”看不到对应模型定义。
    # mapped_model_keys = set(TYPE_TO_MODEL_KEY.values())
    # for model_key, model_class in RESPONSE_MODEL_MAP.items():
    #     # 已由 default_types 显式管理的模型，不重复创建
    #     if model_key in mapped_model_keys:
    #         continue

    #     existing = next(
    #         (
    #             ct for ct in existing_types
    #             if ct.name == model_key or ct.model_name == model_key
    #         ),
    #         None
    #     )

    #     schema = None
    #     try:
    #         schema = model_class.model_json_schema(ref_template="#/$defs/{model}")
    #     except Exception:
    #         schema = None

    #     if existing:
    #         # 仅对内置类型做增量修复，避免覆盖用户自定义类型
    #         if getattr(existing, "built_in", False):
    #             existing.model_name = model_key
    #             if schema is not None:
    #                 existing.json_schema = schema
    #             if not (existing.description or "").strip():
    #                 existing.description = f"{model_key}（内置响应模型）"
    #         continue

    #     auto_type = CardType(
    #         name=model_key,
    #         model_name=model_key,
    #         description=f"{model_key}（内置响应模型）",
    #         json_schema=schema,
    #         ai_params=None,
    #         editor_component=None,
    #         is_ai_enabled=False,
    #         is_singleton=False,
    #         default_ai_context_template=None,
    #         built_in=True,
    #     )
    #     session.add(auto_type)
    #     existing_types.append(auto_type)
    #     existing_type_names.add(model_key)
    #     existing_type_by_name[model_key] = auto_type
    #     logger.info(f"Created builtin response model card type: {model_key}")

    session.commit()
    logger.info("Default card types committed.")
