import re
from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from app.db.models import Card, CardType
from app.schemas.chapter_review import (
    ReviewCardUpsertRequest,
    ReviewDraftResult,
    ReviewResultCardContent,
    ReviewResultCardRead,
    ReviewRunRequest,
    ReviewRunResponse,
)
from app.services import prompt_service
from app.services.ai.core import llm_service
from app.services.review.review_prompt_builders import build_review_prompt

QUALITY_GATE_PATTERN = re.compile(
    r"(?:结论|quality\s*gate)(?:\*\*)?\s*[:：]\s*(?:\*\*)?(pass|revise|block)(?:\*\*)?",
    re.IGNORECASE,
)

DEFAULT_REVIEW_PROFILE = "generic_card_review"
REVIEW_RESULT_CARD_TYPE_NAME = "内容审核卡片"
REVIEW_RESULT_FOLDER_CARD_TYPE_NAME = "文件夹"
REVIEW_RESULT_FOLDER_TITLE = "审核结果"


def parse_quality_gate(result_text: str) -> str:
    match = QUALITY_GATE_PATTERN.search(result_text or "")
    if not match:
        return "revise"
    return match.group(1).lower()


def _get_target_card_or_404(session: Session, card_id: int) -> Card:
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


def _resolve_review_profile_code(review_profile: str | None) -> str:
    normalized = (review_profile or "").strip()
    return normalized or DEFAULT_REVIEW_PROFILE


def _build_system_prompt(session: Session, prompt_name: str) -> str:
    prompt = prompt_service.get_prompt_by_name(session, prompt_name)
    if not prompt or not prompt.template:
        raise HTTPException(status_code=400, detail=f"未找到提示词名称: {prompt_name}")
    return prompt_service.inject_knowledge(session, str(prompt.template))


def _get_review_card_type_or_500(session: Session) -> CardType:
    stmt = select(CardType).where(CardType.name == REVIEW_RESULT_CARD_TYPE_NAME)
    card_type = session.exec(stmt).first()
    if not card_type:
        raise HTTPException(status_code=500, detail=f"缺少卡片类型: {REVIEW_RESULT_CARD_TYPE_NAME}")
    return card_type


def _get_review_folder_card_type(session: Session) -> CardType | None:
    stmt = select(CardType).where(CardType.name == REVIEW_RESULT_FOLDER_CARD_TYPE_NAME)
    return session.exec(stmt).first()


def _get_or_create_review_folder_card(session: Session, project_id: int) -> Card | None:
    folder_type = _get_review_folder_card_type(session)
    if not folder_type:
        return None

    folder = session.exec(
        select(Card).where(
            Card.project_id == project_id,
            Card.card_type_id == folder_type.id,
            Card.parent_id.is_(None),
            Card.title == REVIEW_RESULT_FOLDER_TITLE,
        )
    ).first()
    if folder:
        return folder

    root_cards = session.exec(
        select(Card).where(Card.project_id == project_id, Card.parent_id.is_(None))
    ).all()
    folder = Card(
        title=REVIEW_RESULT_FOLDER_TITLE,
        content={},
        project_id=project_id,
        parent_id=None,
        card_type_id=folder_type.id,
        display_order=len(root_cards),
        ai_context_template=folder_type.default_ai_context_template,
        ai_context_template_review=folder_type.default_ai_context_template_review,
        ai_modified=False,
        needs_confirmation=False,
        last_modified_by="ai",
    )
    session.add(folder)
    session.commit()
    session.refresh(folder)
    return folder


def _resolve_review_card_title(target_title: str) -> str:
    return f"{(target_title or '未命名目标').strip() or '未命名目标'} · 审核结果"


def _build_review_card_content(
    *,
    target_card_id: int,
    target_title: str,
    review_type: str,
    review_profile: str,
    target_field: str | None,
    review_text: str,
    quality_gate: str,
    prompt_name: str,
    llm_config_id: int | None,
    content_snapshot: str | None,
    meta: dict | None,
) -> dict:
    payload = ReviewResultCardContent(
        review_target_card_id=target_card_id,
        review_target_title=target_title,
        review_type=review_type,  # type: ignore[arg-type]
        review_profile=review_profile,
        review_target_field=target_field,
        quality_gate=quality_gate,  # type: ignore[arg-type]
        review_markdown=review_text,
        prompt_name=prompt_name,
        llm_config_id=llm_config_id,
        reviewed_at=datetime.now().isoformat(),
        target_snapshot=content_snapshot,
        meta=meta or {},
    )
    return payload.model_dump()


def _card_to_review_result(card: Card) -> ReviewResultCardRead:
    content = dict(card.content or {})
    return ReviewResultCardRead(
        card_id=card.id,
        project_id=card.project_id,
        title=card.title,
        review_target_card_id=int(content.get("review_target_card_id")),
        review_target_title=str(content.get("review_target_title") or ""),
        review_target_type=str(content.get("review_target_type") or "card"),  # type: ignore[arg-type]
        review_type=str(content.get("review_type") or "card"),  # type: ignore[arg-type]
        review_profile=str(content.get("review_profile") or DEFAULT_REVIEW_PROFILE),
        review_target_field=content.get("review_target_field"),
        quality_gate=str(content.get("quality_gate") or "revise"),  # type: ignore[arg-type]
        review_markdown=str(content.get("review_markdown") or ""),
        prompt_name=str(content.get("prompt_name") or ""),
        llm_config_id=content.get("llm_config_id"),
        reviewed_at=str(content.get("reviewed_at") or ""),
        target_snapshot=content.get("target_snapshot"),
        meta=dict(content.get("meta") or {}),
        created_at=card.created_at,
    )


def _find_review_result_cards(
    session: Session,
    *,
    project_id: int,
    target_card_id: Optional[int] = None,
) -> List[Card]:
    review_card_type = _get_review_card_type_or_500(session)
    cards = session.exec(
        select(Card)
        .where(Card.project_id == project_id, Card.card_type_id == review_card_type.id)
        .order_by(Card.created_at.desc())
    ).all()

    filtered: List[Card] = []
    for card in cards:
        content = dict(card.content or {})
        if target_card_id is not None and int(content.get("review_target_card_id") or -1) != target_card_id:
            continue
        filtered.append(card)
    return filtered


def _find_existing_review_card(
    session: Session,
    *,
    project_id: int,
    target_card_id: int,
    review_profile: str,
    target_field: str | None,
    prompt_name: str,
) -> Optional[Card]:
    candidates = _find_review_result_cards(
        session,
        project_id=project_id,
        target_card_id=target_card_id,
    )
    for card in candidates:
        content = dict(card.content or {})
        if str(content.get("review_profile") or "") != review_profile:
            continue
        if (content.get("review_target_field") or None) != target_field:
            continue
        if str(content.get("prompt_name") or "") != prompt_name:
            continue
        return card
    return None


def _build_draft_result(
    *,
    session: Session,
    project_id: int,
    target_card_id: int,
    target_title: str,
    review_type: str,
    review_profile: str,
    target_field: str | None,
    review_text: str,
    prompt_name: str,
    llm_config_id: int | None,
    content_snapshot: str | None,
    meta: dict | None,
) -> ReviewDraftResult:
    existing_card = _find_existing_review_card(
        session,
        project_id=project_id,
        target_card_id=target_card_id,
        review_profile=review_profile,
        target_field=target_field,
        prompt_name=prompt_name,
    )
    return ReviewDraftResult(
        review_text=review_text,
        quality_gate=parse_quality_gate(review_text),  # type: ignore[arg-type]
        review_type=review_type,  # type: ignore[arg-type]
        review_profile=review_profile,
        review_target_field=target_field,
        prompt_name=prompt_name,
        llm_config_id=llm_config_id,
        target_snapshot=content_snapshot,
        existing_review_card_id=existing_card.id if existing_card else None,
        review_card_title=_resolve_review_card_title(target_title),
        meta=meta or {},
    )


async def run_review(session: Session, request: ReviewRunRequest) -> ReviewRunResponse:
    card = _get_target_card_or_404(session, request.card_id)
    project_id = request.project_id or getattr(card, "project_id", None)
    if not project_id:
        raise HTTPException(status_code=400, detail="缺少 project_id")

    review_profile = _resolve_review_profile_code(request.review_profile)
    prompt_name = request.prompt_name or "通用审核"
    system_prompt = _build_system_prompt(session, prompt_name)
    user_prompt = build_review_prompt(request)

    try:
        review_text = await llm_service.generate_review(
            session=session,
            llm_config_id=request.llm_config_id,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            timeout=request.timeout,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    draft = _build_draft_result(
        session=session,
        project_id=project_id,
        target_card_id=request.card_id,
        target_title=request.title,
        review_type=request.review_type,
        review_profile=review_profile,
        target_field=request.target_field,
        review_text=review_text,
        prompt_name=prompt_name,
        llm_config_id=request.llm_config_id,
        content_snapshot=request.content_snapshot,
        meta=request.meta,
    )
    return ReviewRunResponse(review_text=review_text, draft=draft)


def upsert_review_result_card(session: Session, request: ReviewCardUpsertRequest) -> ReviewResultCardRead:
    review_card_type = _get_review_card_type_or_500(session)
    review_folder = _get_or_create_review_folder_card(session, request.project_id)
    review_profile = _resolve_review_profile_code(request.review_profile)
    existing_card = _find_existing_review_card(
        session,
        project_id=request.project_id,
        target_card_id=request.target_card_id,
        review_profile=review_profile,
        target_field=request.target_field,
        prompt_name=request.prompt_name,
    )

    content = _build_review_card_content(
        target_card_id=request.target_card_id,
        target_title=request.target_title,
        review_type=request.review_type,
        review_profile=review_profile,
        target_field=request.target_field,
        review_text=request.review_text,
        quality_gate=request.quality_gate,
        prompt_name=request.prompt_name,
        llm_config_id=request.llm_config_id,
        content_snapshot=request.content_snapshot,
        meta=request.meta,
    )
    title = _resolve_review_card_title(request.target_title)

    if existing_card:
        if review_folder and existing_card.parent_id != review_folder.id:
            sibling_cards = session.exec(
                select(Card).where(
                    Card.project_id == request.project_id,
                    Card.parent_id == review_folder.id,
                    Card.id != existing_card.id,
                )
            ).all()
            existing_card.parent_id = review_folder.id
            existing_card.display_order = len(sibling_cards)
        existing_card.title = title
        existing_card.content = content
        existing_card.needs_confirmation = False
        existing_card.ai_modified = False
        existing_card.last_modified_by = "ai"
        session.add(existing_card)
        session.commit()
        session.refresh(existing_card)
        return _card_to_review_result(existing_card)

    sibling_cards = session.exec(
        select(Card).where(
            Card.project_id == request.project_id,
            Card.parent_id == (review_folder.id if review_folder else None),
        )
    ).all()
    card = Card(
        title=title,
        content=content,
        project_id=request.project_id,
        parent_id=review_folder.id if review_folder else None,
        card_type_id=review_card_type.id,
        display_order=len(sibling_cards),
        ai_context_template=review_card_type.default_ai_context_template,
        ai_context_template_review=review_card_type.default_ai_context_template_review,
        ai_modified=False,
        needs_confirmation=False,
        last_modified_by="ai",
    )
    session.add(card)
    session.commit()
    session.refresh(card)
    return _card_to_review_result(card)


def list_reviews_by_card(session: Session, card_id: int) -> List[ReviewResultCardRead]:
    target_card = _get_target_card_or_404(session, card_id)
    cards = _find_review_result_cards(
        session,
        project_id=target_card.project_id,
        target_card_id=card_id,
    )
    return [_card_to_review_result(card) for card in cards]


def delete_review_result_card(session: Session, review_card_id: int) -> bool:
    card = session.get(Card, review_card_id)
    if not card:
        return False
    review_card_type = _get_review_card_type_or_500(session)
    if card.card_type_id != review_card_type.id:
        raise HTTPException(status_code=400, detail="目标卡片不是审核结果卡片")
    session.delete(card)
    session.commit()
    return True
