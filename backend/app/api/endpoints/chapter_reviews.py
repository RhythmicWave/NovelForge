from typing import List

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.chapter_review import (
    ReviewCardUpsertRequest,
    ReviewResultCardRead,
    ReviewRunRequest,
    ReviewRunResponse,
)
from app.schemas.response import ApiResponse
from app.services.review.review_service import (
    delete_review_result_card,
    list_reviews_by_card,
    run_review,
    upsert_review_result_card,
)


router = APIRouter()


@router.post(
    "/cards/run",
    response_model=ApiResponse[ReviewRunResponse],
    summary="运行卡片审核（返回审核草稿）",
)
async def run_review_endpoint(
    request: ReviewRunRequest,
    session: Session = Depends(get_session),
):
    result = await run_review(session, request)
    return ApiResponse(data=result)


@router.post(
    "/cards/upsert",
    response_model=ApiResponse[ReviewResultCardRead],
    summary="创建或更新审核结果卡片",
)
def upsert_review_card_endpoint(
    request: ReviewCardUpsertRequest,
    session: Session = Depends(get_session),
):
    card = upsert_review_result_card(session, request)
    return ApiResponse(data=card)


@router.get(
    "/cards/{card_id}",
    response_model=ApiResponse[List[ReviewResultCardRead]],
    summary="获取某张卡片绑定的审核结果卡片",
)
def list_review_cards_by_target_endpoint(
    card_id: int,
    session: Session = Depends(get_session),
):
    return ApiResponse(data=list_reviews_by_card(session, card_id))


@router.delete(
    "/{review_card_id}",
    response_model=ApiResponse[bool],
    summary="删除审核结果卡片",
)
def delete_review_card_endpoint(
    review_card_id: int,
    session: Session = Depends(get_session),
):
    return ApiResponse(data=delete_review_result_card(session, review_card_id))
