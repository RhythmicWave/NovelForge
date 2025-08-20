from fastapi import APIRouter, Depends
from typing import Any
from sqlmodel import Session

from app.db.session import get_session
from app.services.context_service import assemble_context, ContextAssembleParams
from app.schemas.context import AssembleContextRequest, AssembleContextResponse

router = APIRouter()

@router.post("/assemble", response_model=AssembleContextResponse, summary="装配写作上下文（事实子图）")
def assemble(req: AssembleContextRequest, session: Session = Depends(get_session)):
    params = ContextAssembleParams(
        project_id=req.project_id,
        volume_number=req.volume_number,
        chapter_number=req.chapter_number,
        chapter_id=req.chapter_id,
        participants=req.participants,
        current_draft_tail=req.current_draft_tail,
    )
    ctx = assemble_context(session, params)
    return AssembleContextResponse(**ctx.__dict__)
