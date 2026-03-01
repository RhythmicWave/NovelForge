from __future__ import annotations

import re
from typing import List

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

    merged_context = _merge_facts_into_context(request.context_info, assembled.facts_subgraph)
    logger.debug(
        "[续写上下文] 自动组装事实子图完成 project_id={} participants={} facts_len={}",
        request.project_id,
        len(participants),
        len(assembled.facts_subgraph or ""),
    )
    return merged_context
