from __future__ import annotations

import re
from typing import Any, Dict, List

from loguru import logger
from sqlmodel import Session

from app.schemas.ai import ContinuationRequest
from app.services.context_service import ContextAssembleParams, assemble_context


_FACTS_SECTION_PATTERN = re.compile(r"【事实子图】\n.*?(?=(?:\n\n【)|\Z)", flags=re.S)


def _normalize_participants(participants: List[str] | None) -> List[str]:
    if not participants:
        return []
    cleaned: List[str] = []
    for item in participants:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if name:
            cleaned.append(name)
    return cleaned


def _merge_facts_into_context(context_info: str | None, facts_subgraph: str | None) -> str:
    raw_context = (context_info or "").strip()
    facts = (facts_subgraph or "").strip()

    if not facts:
        return raw_context

    facts_block = f"【事实子图】\n{facts}"
    if not raw_context:
        return facts_block

    if _FACTS_SECTION_PATTERN.search(raw_context):
        return _FACTS_SECTION_PATTERN.sub(facts_block, raw_context, count=1)
    return f"{raw_context}\n\n{facts_block}"


def _to_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    return {}


def _format_facts_structured(facts_structured: Any) -> str:
    payload = _to_dict(facts_structured)
    if not payload:
        return ""

    lines: List[str] = []
    fact_summaries = payload.get("fact_summaries")
    if isinstance(fact_summaries, list) and fact_summaries:
        lines.append("关键事实：")
        for item in fact_summaries:
            text = str(item or "").strip()
            if text:
                lines.append(f"- {text}")

    relation_summaries = payload.get("relation_summaries")
    if isinstance(relation_summaries, list) and relation_summaries:
        lines.append("关系摘要：")
        for rel in relation_summaries:
            relation = _to_dict(rel)
            a = str(relation.get("a") or "").strip()
            b = str(relation.get("b") or "").strip()
            kind = str(relation.get("kind") or "其他").strip() or "其他"
            lines.append(f"- {a} ↔ {b}（{kind}）")

            description = str(relation.get("description") or "").strip()
            if description:
                lines.append(f"  · {description}")

            a_to_b = str(relation.get("a_to_b_addressing") or "").strip()
            b_to_a = str(relation.get("b_to_a_addressing") or "").strip()
            addressing_parts: List[str] = []
            if a_to_b:
                addressing_parts.append(f"A称B：{a_to_b}")
            if b_to_a:
                addressing_parts.append(f"B称A：{b_to_a}")
            if addressing_parts:
                lines.append(f"  · {' ｜ '.join(addressing_parts)}")

            recent_dialogues = relation.get("recent_dialogues")
            if isinstance(recent_dialogues, list) and recent_dialogues:
                lines.append("  · 对话样例：")
                for dialogue in recent_dialogues:
                    text = str(dialogue or "").strip()
                    if text:
                        lines.append(f"    - {text}")

            recent_events = relation.get("recent_event_summaries")
            if isinstance(recent_events, list) and recent_events:
                lines.append("  · 近期事件：")
                for event in recent_events:
                    item = _to_dict(event)
                    summary = str(item.get("summary") or "").strip()
                    if not summary:
                        continue
                    tags: List[str] = []
                    if item.get("volume_number") is not None:
                        tags.append(f"卷{item.get('volume_number')}")
                    if item.get("chapter_number") is not None:
                        tags.append(f"章{item.get('chapter_number')}")
                    if tags:
                        lines.append(f"    - {summary}（{' '.join(tags)}）")
                    else:
                        lines.append(f"    - {summary}")

    character_summaries = payload.get("character_summaries")
    if isinstance(character_summaries, list) and character_summaries:
        lines.append("角色设定（必须严格一致，违反=OOC）：")
        for ch in character_summaries:
            ch_dict = _to_dict(ch)
            name = str(ch_dict.get("name") or "").strip()
            if not name:
                continue
            role_type = str(ch_dict.get("role_type") or "").strip()
            name_part = f"{name}（{role_type}）" if role_type else name
            lines.append(f"- {name_part}")
            description = str(ch_dict.get("description") or "").strip()
            if description:
                lines.append(f"  · 简介：{description}")
            personality = str(ch_dict.get("personality") or "").strip()
            if personality:
                lines.append(f"  · 性格：{personality}")
            core_drive = str(ch_dict.get("core_drive") or "").strip()
            if core_drive:
                lines.append(f"  · 动机：{core_drive}")
            constraints = str(ch_dict.get("constraints") or "").strip()
            if constraints:
                lines.append(f"  · 铁律：{constraints}")

    item_summaries = payload.get("item_summaries")
    if isinstance(item_summaries, list) and item_summaries:
        lines.append("物品设定（必须严格一致）：")
        for item in item_summaries:
            item_dict = _to_dict(item)
            name = str(item_dict.get("name") or "").strip()
            if not name:
                continue
            category = str(item_dict.get("category") or "").strip()
            name_part = f"{name}（{category}）" if category else name
            lines.append(f"- {name_part}")
            description = str(item_dict.get("description") or "").strip()
            if description:
                lines.append(f"  · 简介：{description}")
            owner_hint = str(item_dict.get("owner_hint") or "").strip()
            if owner_hint:
                lines.append(f"  · 归属：{owner_hint}")
            power = str(item_dict.get("power_or_effect") or "").strip()
            if power:
                lines.append(f"  · 能力/效果：{power}")
            constraints = str(item_dict.get("constraints") or "").strip()
            if constraints:
                lines.append(f"  · 铁律：{constraints}")

    concept_summaries = payload.get("concept_summaries")
    if isinstance(concept_summaries, list) and concept_summaries:
        lines.append("概念设定：")
        for concept in concept_summaries:
            concept_dict = _to_dict(concept)
            name = str(concept_dict.get("name") or "").strip()
            if not name:
                continue
            lines.append(f"- {name}")
            description = str(concept_dict.get("description") or "").strip()
            if description:
                lines.append(f"  · {description}")
            rule_definition = str(concept_dict.get("rule_definition") or "").strip()
            if rule_definition:
                lines.append(f"  · 规则：{rule_definition}")

    return "\n".join(lines).strip()


def enrich_continuation_context_info(session: Session, request: ContinuationRequest) -> str:
    """服务端自动组装事实子图，并合并到续写上下文。"""
    participants = _normalize_participants(request.participants)

    if not request.project_id:
        logger.debug("[续写上下文] project_id 为空，跳过事实子图自动组装")
        return (request.context_info or "").strip()

    if not participants:
        logger.debug("[续写上下文] participants 为空，跳过事实子图自动组装")
        return (request.context_info or "").strip()

    try:
        assembled = assemble_context(
            session,
            ContextAssembleParams(
                project_id=request.project_id,
                volume_number=request.volume_number,
                chapter_number=request.chapter_number,
                chapter_id=None,
                participants=participants,
                current_draft_tail=None,
            ),
        )
    except Exception as exc:
        logger.warning("[续写上下文] 自动组装事实子图失败: {}", exc)
        return (request.context_info or "").strip()

    structured_facts = _format_facts_structured(assembled.facts_structured)
    merged_context = _merge_facts_into_context(
        request.context_info,
        structured_facts or assembled.facts_subgraph,
    )
    logger.debug(
        "[续写上下文] 自动组装事实子图完成 project_id={} participants={} facts_len={} structured={}",
        request.project_id,
        len(participants),
        len(structured_facts or assembled.facts_subgraph or ""),
        bool(structured_facts),
    )
    return merged_context
