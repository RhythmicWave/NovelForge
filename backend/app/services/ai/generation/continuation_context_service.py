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
