"""Schema 服务层

负责 Schema 的组装、引用解析、$defs 补全等业务逻辑。
"""

import re
from typing import Dict, Any, Set
from copy import deepcopy
from sqlmodel import Session
from app.db.models import CardType
from app.schemas.entity import DYNAMIC_INFO_TYPES
from app.schemas import entity as entity_schemas
from loguru import logger


# --- Schema 引用收集 ---

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
    "world_view_thinking": "世界观设计思考",
    "world_view": "世界观",
    "title": "标题",
    "entity_type": "实体类型",
    "life_span": "生命跨度",
    "role_type": "角色类型",
    "born_scene": "出生场景",
    "personality": "性格",
    "core_drive": "核心驱动力",
    "character_arc": "角色弧光",
    "influence": "影响力",
    "relationship": "关系",
    "dynamic_info": "动态信息",
    "last_appearance": "最后出场时间",
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

    candidate = re.split(r"[，。；;！？:：\n（(]", desc, maxsplit=1)[0].strip()
    if not candidate:
        return None
    if len(candidate) > 16:
        candidate = candidate[:16].strip()
    return candidate or None


def localize_schema_titles(schema: Any) -> Any:
    """将 schema 字段标题本地化为中文（不修改字段 key）。"""
    if not isinstance(schema, (dict, list)):
        return schema

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                for field_name, field_schema in properties.items():
                    if isinstance(field_schema, dict):
                        current_title = str(field_schema.get("title") or "")
                        if not _contains_cjk(current_title):
                            localized = FIELD_TITLE_ZH_MAP.get(field_name) or _derive_title_from_description(
                                field_schema.get("description")
                            )
                            if localized:
                                field_schema["title"] = localized

            for defs_key in ("$defs", "definitions"):
                defs = node.get(defs_key)
                if isinstance(defs, dict):
                    for def_schema in defs.values():
                        visit(def_schema)

            items = node.get("items")
            if isinstance(items, dict):
                visit(items)

            prefix_items = node.get("prefixItems")
            if isinstance(prefix_items, list):
                for item in prefix_items:
                    visit(item)

            for union_key in ("anyOf", "oneOf", "allOf"):
                variants = node.get(union_key)
                if isinstance(variants, list):
                    for variant in variants:
                        visit(variant)

            for value in node.values():
                if isinstance(value, (dict, list)):
                    visit(value)

        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(schema)
    return schema

def collect_ref_names(node: Any) -> Set[str]:
    """递归收集 Schema 中的所有 $ref 引用名称
    
    Args:
        node: Schema 节点（dict/list/其他）
        
    Returns:
        引用名称集合
    """
    names: Set[str] = set()
    if isinstance(node, dict):
        if '$ref' in node and isinstance(node['$ref'], str) and node['$ref'].startswith('#/$defs/'):
            names.add(node['$ref'].split('/')[-1])
        for v in node.values():
            names |= collect_ref_names(v)
    elif isinstance(node, list):
        for it in node:
            names |= collect_ref_names(it)
    return names


# --- 内置模型 $defs 缓存 ---

_BUILTIN_DEFS_CACHE: Dict[str, Any] | None = None

def get_builtin_defs() -> Dict[str, Any]:
    """获取所有内置 Pydantic 模型的 $defs（带缓存）
    
    Returns:
        合并后的 $defs 字典
    """
    global _BUILTIN_DEFS_CACHE
    if _BUILTIN_DEFS_CACHE is not None:
        return _BUILTIN_DEFS_CACHE
    
    # 导入响应模型映射
    from app.schemas.response_registry import RESPONSE_MODEL_MAP
    
    merged: Dict[str, Any] = {}
    for _, model_class in RESPONSE_MODEL_MAP.items():
        sch = model_class.model_json_schema(ref_template="#/$defs/{model}")
        sch = localize_schema_titles(sch)
        defs = sch.get('$defs') or {}
        merged.update(defs)
    
    _BUILTIN_DEFS_CACHE = merged
    return merged


def augment_schema_with_builtin_defs(schema: Dict[str, Any]) -> Dict[str, Any]:
    """将内置模型的 $defs 注入到自定义 Schema 中
    
    Args:
        schema: 原始 Schema
        
    Returns:
        增强后的 Schema（深拷贝）
    """
    sch = deepcopy(schema) if schema is not None else {}
    if not isinstance(sch, dict):
        return sch
    
    # 收集所有引用
    ref_names = collect_ref_names(sch)
    if not ref_names:
        return localize_schema_titles(sch)
    
    # 获取内置 defs
    builtin_defs = get_builtin_defs()
    
    # 确保有 $defs
    if '$defs' not in sch:
        sch['$defs'] = {}
    
    # 注入被引用的内置定义
    for name in ref_names:
        if name in builtin_defs and name not in sch['$defs']:
            sch['$defs'][name] = builtin_defs[name]

    return localize_schema_titles(sch)


# --- CardType Schema 组装 ---

def compose_schema_with_card_types(session: Session, schema: Dict[str, Any]) -> Dict[str, Any]:
    """将 CardType 的 Schema 注入到 $defs 中
    
    Args:
        session: 数据库会话
        schema: 原始 Schema
        
    Returns:
        增强后的 Schema（深拷贝）
    """
    sch = deepcopy(schema) if isinstance(schema, dict) else {}
    if not isinstance(sch, dict):
        return sch
    
    # 确保有 $defs
    if '$defs' not in sch:
        sch['$defs'] = {}
    
    # 收集所有引用
    ref_names = collect_ref_names(sch)
    if not ref_names:
        return localize_schema_titles(sch)
    
    # 查询所有 CardType，建立映射
    all_types = session.query(CardType).all()
    by_model: Dict[str, Any] = {}
    
    for ct in all_types:
        if ct and ct.json_schema:
            localized_schema = localize_schema_titles(deepcopy(ct.json_schema))
            if ct.model_name:
                by_model[ct.model_name] = localized_schema
            by_model[ct.name] = localized_schema
    
    # 注入被引用的 CardType Schema
    for name in ref_names:
        if name in by_model:
            sch['$defs'][name] = by_model[name]

    return localize_schema_titles(sch)


def compose_full_schema(session: Session, schema: Dict[str, Any]) -> Dict[str, Any]:
    """完整的 Schema 组装：内置 defs + CardType defs
    
    Args:
        session: 数据库会话
        schema: 原始 Schema
        
    Returns:
        完全增强后的 Schema
    """
    # 先注入内置 defs
    sch = augment_schema_with_builtin_defs(schema)
    # 再注入 CardType defs
    sch = compose_schema_with_card_types(session, sch)
    return localize_schema_titles(sch)
