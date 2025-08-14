from fastapi import APIRouter

from app.services.consistency_service import ConsistencyService
from app.schemas.consistency import CheckRequest, CheckResponse, Issue, FixSuggestion

router = APIRouter()

@router.post("/check", response_model=CheckResponse, summary="一致性校验（精简版：基于结构化事实）")
def check(req: CheckRequest) -> CheckResponse:
    svc = ConsistencyService()
    res = svc.check(req.text, req.facts_structured or {})
    # 规范化
    issues = [Issue(type=i.get("type", "generic"), message=i.get("message", ""), position=i.get("position")) for i in res.get("issues", [])]
    fixes = [FixSuggestion(range=f.get("range"), replacement=f.get("replacement", "")) for f in res.get("suggested_fixes", [])]
    return CheckResponse(issues=issues, suggested_fixes=fixes) 