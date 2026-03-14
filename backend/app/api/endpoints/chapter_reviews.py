import re
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.db.models import Card, ReviewRecord
from app.db.session import get_session
from app.schemas.chapter_review import (
    ChapterReviewRunRequest,
    ChapterReviewRunResponse,
    ReviewRecordRead,
    StageReviewRunRequest,
    StageReviewRunResponse,
)
from app.schemas.response import ApiResponse
from app.services import prompt_service
from app.services.ai.core import llm_service


router = APIRouter()

_QUALITY_GATE_PATTERN = re.compile(
    r"结论(?:\*\*)?\s*[:：]\s*(?:\*\*)?(pass|revise|block)(?:\*\*)?",
    re.IGNORECASE,
)


def _count_words(text: str) -> int:
    return len((text or "").replace(" ", "").replace("\n", ""))


def _build_review_user_prompt(request: ChapterReviewRunRequest) -> str:
    parts: list[str] = []

    chapter_meta = [
        f"标题：{request.title}",
        f"卷号：{request.volume_number}" if request.volume_number is not None else "",
        f"章节号：{request.chapter_number}" if request.chapter_number is not None else "",
        f"参与实体：{'、'.join(request.participants)}" if request.participants else "",
        f"正文字数：{_count_words(request.chapter_content)}",
    ]
    parts.append("【章节信息】\n" + "\n".join(line for line in chapter_meta if line))

    if request.previous_chapters:
        previous_blocks = []
        for item in request.previous_chapters:
            label = " / ".join(
                str(x)
                for x in [
                    f"卷{item.volume_number}" if item.volume_number is not None else None,
                    f"章{item.chapter_number}" if item.chapter_number is not None else None,
                    item.title or None,
                ]
                if x
            )
            previous_blocks.append(f"### {label or '前文章节'}\n{item.content}")
        parts.append("【前文参考】\n" + "\n\n".join(previous_blocks))

    if request.context_info:
        parts.append(f"【引用上下文】\n{request.context_info.strip()}")

    if request.facts_info:
        parts.append(f"【已知事实子图】\n{request.facts_info.strip()}")

    parts.append(f"【正文】\n{(request.chapter_content or '').strip()}")
    return "\n\n".join(parts)


def _parse_quality_gate(result_text: str) -> str:
    match = _QUALITY_GATE_PATTERN.search(result_text or "")
    if not match:
        return "revise"
    return match.group(1).lower()


def _build_stage_review_user_prompt(request: StageReviewRunRequest) -> str:
    parts: list[str] = []

    reference_text = ""
    if len(request.reference_chapter) >= 2:
        reference_text = f"{request.reference_chapter[0]} - {request.reference_chapter[1]}"
    elif len(request.reference_chapter) == 1:
        reference_text = str(request.reference_chapter[0])

    stage_meta = [
        f"标题：{request.title}",
        f"阶段名：{request.stage_name}" if request.stage_name else "",
        f"卷号：{request.volume_number}" if request.volume_number is not None else "",
        f"阶段号：{request.stage_number}" if request.stage_number is not None else "",
        f"参考章节范围：{reference_text}" if reference_text else "",
    ]
    parts.append("【阶段信息】\n" + "\n".join(line for line in stage_meta if line))

    stage_body = []
    if request.analysis:
        stage_body.append(f"阶段分析：\n{request.analysis.strip()}")
    if request.overview:
        stage_body.append(f"阶段概述：\n{request.overview.strip()}")
    if request.entity_snapshot:
        stage_body.append("阶段末实体快照：\n" + "\n".join(f"- {item}" for item in request.entity_snapshot if item))
    if stage_body:
        parts.append("【当前阶段内容】\n" + "\n\n".join(stage_body))

    if request.previous_stages:
        previous_blocks = []
        for item in request.previous_stages:
            previous_reference = ""
            if len(item.reference_chapter) >= 2:
                previous_reference = f"{item.reference_chapter[0]} - {item.reference_chapter[1]}"
            elif len(item.reference_chapter) == 1:
                previous_reference = str(item.reference_chapter[0])
            meta = " / ".join(
                value
                for value in [
                    f"卷{item.volume_number}" if item.volume_number is not None else "",
                    f"阶段{item.stage_number}" if item.stage_number is not None else "",
                    item.stage_name or item.title,
                    previous_reference,
                ]
                if value
            )
            block_lines = [item.overview.strip()] if item.overview else []
            if item.analysis:
                block_lines.append(f"分析：{item.analysis.strip()}")
            if item.entity_snapshot:
                block_lines.append("阶段末实体快照：\n" + "\n".join(f"- {snapshot}" for snapshot in item.entity_snapshot if snapshot))
            previous_blocks.append(f"### {meta or '上一阶段'}\n" + "\n".join(line for line in block_lines if line))
        parts.append("【上一阶段参考】\n" + "\n\n".join(previous_blocks))

    if request.chapter_outlines:
        chapter_blocks = []
        for item in request.chapter_outlines:
            meta = " / ".join(
                value
                for value in [
                    f"第{item.chapter_number}章" if item.chapter_number is not None else "",
                    item.title,
                ]
                if value
            )
            extra_lines = [item.overview.strip()] if item.overview else []
            if item.entity_list:
                extra_lines.append("出场实体：" + "、".join(entity for entity in item.entity_list if entity))
            extra_lines.append(f"是否已有正文：{'是' if item.has_content else '否'}")
            if item.word_count is not None:
                extra_lines.append(f"正文字数：{item.word_count}")
            chapter_blocks.append(f"### {meta or '章节'}\n" + "\n".join(extra_lines))
        parts.append("【本阶段章节列表】\n" + "\n\n".join(chapter_blocks))

    if request.context_info:
        parts.append(f"【引用上下文】\n{request.context_info.strip()}")

    if request.facts_info:
        parts.append(f"【已知事实子图】\n{request.facts_info.strip()}")
    return "\n\n".join(parts)


def _save_review_record(
    *,
    session: Session,
    project_id: int,
    review_type: str,
    target_id: int,
    target_title: str,
    prompt_name: str,
    llm_config_id: int,
    review_text: str,
    content_snapshot: str | None,
) -> ReviewRecord:
    record = ReviewRecord(
        project_id=project_id,
        review_type=review_type,
        target_type="card",
        target_id=target_id,
        target_title=target_title,
        prompt_name=prompt_name,
        llm_config_id=llm_config_id,
        quality_gate=_parse_quality_gate(review_text),
        result_text=review_text,
        content_snapshot=content_snapshot,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.post(
    "/run",
    response_model=ApiResponse[ChapterReviewRunResponse],
    summary="运行章节审核并记录结果",
)
async def run_chapter_review(
    request: ChapterReviewRunRequest,
    session: Session = Depends(get_session),
):
    card = session.get(Card, request.card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    project_id = request.project_id or getattr(card, "project_id", None)
    if not project_id:
        raise HTTPException(status_code=400, detail="缺少 project_id")

    prompt = prompt_service.get_prompt_by_name(session, request.prompt_name)
    if not prompt or not prompt.template:
        raise HTTPException(status_code=400, detail=f"未找到提示词名称: {request.prompt_name}")

    system_prompt = prompt_service.inject_knowledge(session, str(prompt.template))
    user_prompt = _build_review_user_prompt(request)

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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    record = _save_review_record(
        session=session,
        project_id=project_id,
        review_type="chapter",
        target_id=request.card_id,
        target_title=request.title,
        prompt_name=request.prompt_name,
        llm_config_id=request.llm_config_id,
        review_text=review_text,
        content_snapshot=request.content_snapshot,
    )

    return ApiResponse(data=ChapterReviewRunResponse(
        review_text=review_text,
        record=ReviewRecordRead.model_validate(record),
    ))


@router.post(
    "/stage/run",
    response_model=ApiResponse[StageReviewRunResponse],
    summary="运行阶段审核并记录结果",
)
async def run_stage_review(
    request: StageReviewRunRequest,
    session: Session = Depends(get_session),
):
    card = session.get(Card, request.card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    project_id = request.project_id or getattr(card, "project_id", None)
    if not project_id:
        raise HTTPException(status_code=400, detail="缺少 project_id")

    prompt = prompt_service.get_prompt_by_name(session, request.prompt_name)
    if not prompt or not prompt.template:
        raise HTTPException(status_code=400, detail=f"未找到提示词名称: {request.prompt_name}")

    system_prompt = prompt_service.inject_knowledge(session, str(prompt.template))
    user_prompt = _build_stage_review_user_prompt(request)

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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    record = _save_review_record(
        session=session,
        project_id=project_id,
        review_type="stage",
        target_id=request.card_id,
        target_title=request.title,
        prompt_name=request.prompt_name,
        llm_config_id=request.llm_config_id,
        review_text=review_text,
        content_snapshot=request.content_snapshot,
    )

    return ApiResponse(data=StageReviewRunResponse(
        review_text=review_text,
        record=ReviewRecordRead.model_validate(record),
    ))


@router.get(
    "/cards/{card_id}",
    response_model=ApiResponse[List[ReviewRecordRead]],
    summary="获取某张正文卡片的审核记录",
)
def list_chapter_reviews(
    card_id: int,
    session: Session = Depends(get_session),
):
    records = session.exec(
        select(ReviewRecord)
        .where(ReviewRecord.review_type == "chapter", ReviewRecord.target_type == "card", ReviewRecord.target_id == card_id)
        .order_by(ReviewRecord.created_at.desc())
    ).all()
    return ApiResponse(data=[ReviewRecordRead.model_validate(item) for item in records])


@router.get(
    "/projects/{project_id}",
    response_model=ApiResponse[List[ReviewRecordRead]],
    summary="获取项目审核历史",
)
def list_project_reviews(
    project_id: int,
    review_type: Literal["all", "chapter", "stage"] = Query(default="all"),
    target_title: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    query = (
        select(ReviewRecord)
        .where(ReviewRecord.project_id == project_id)
        .order_by(ReviewRecord.created_at.desc())
    )

    if review_type != "all":
        query = query.where(ReviewRecord.review_type == review_type)

    normalized_target_title = (target_title or "").strip()
    if normalized_target_title:
        query = query.where(ReviewRecord.target_title.contains(normalized_target_title))

    records = session.exec(query).all()
    return ApiResponse(data=[ReviewRecordRead.model_validate(item) for item in records])


@router.delete(
    "/{review_id}",
    response_model=ApiResponse[bool],
    summary="删除审核记录",
)
def delete_review(
    review_id: int,
    session: Session = Depends(get_session),
):
    record = session.get(ReviewRecord, review_id)
    if not record:
        raise HTTPException(status_code=404, detail="Review record not found")

    session.delete(record)
    session.commit()
    return ApiResponse(data=True)
