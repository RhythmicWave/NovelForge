from fastapi import APIRouter, Depends
from typing import Any
from sqlmodel import Session

from app.db.session import get_session
from app.services.context_service import assemble_context, ContextAssembleParams, get_settings, update_settings
from app.schemas.context import AssembleContextRequest, AssembleContextResponse, ContextSettingsModel, UpdateContextSettingsRequest

router = APIRouter()

@router.post("/assemble", response_model=AssembleContextResponse, summary="装配写作上下文（更早摘要 + 事实子图 + 最近原文）")
def assemble(req: AssembleContextRequest, session: Session = Depends(get_session)):
    params = ContextAssembleParams(
        project_id=req.project_id,
        volume_number=req.volume_number,
        chapter_number=req.chapter_number,
        chapter_id=req.chapter_id,
        participants=req.participants,
        current_draft_tail=req.current_draft_tail,
        recent_chapters_window=req.recent_chapters_window or get_settings().recent_chapters_window,
    )
    ctx = assemble_context(session, params)
    return AssembleContextResponse(**ctx.__dict__)

@router.get("/settings", response_model=ContextSettingsModel, summary="获取上下文装配设置")
def get_context_settings():
    s = get_settings()
    return ContextSettingsModel(**s.__dict__)

@router.post("/settings", response_model=ContextSettingsModel, summary="更新上下文装配设置（部分字段）")
def update_context_settings(req: UpdateContextSettingsRequest):
    patch = {k: v for k, v in req.model_dump().items() if v is not None}
    s = update_settings(patch)
    return ContextSettingsModel(**s.__dict__) 