from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from sqlmodel import Session
from app.db.session import get_session
from app.schemas.prompt import PromptRead, PromptCreate, PromptUpdate
from app.schemas.response import ApiResponse
from app.services import prompt_service

router = APIRouter()

@router.post("/", response_model=ApiResponse[PromptRead], summary="创建新提示词")
def create_prompt(
    *,
    session: Session = Depends(get_session),
    prompt: PromptCreate,
):
    """
    创建一个新的提示词模板。
    """
    try:
        new_prompt = prompt_service.create_prompt(session=session, prompt_create=prompt)
        return ApiResponse(data=new_prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=ApiResponse[List[PromptRead]], summary="获取提示词列表")
def read_prompts(
    *,
    session: Session = Depends(get_session),
    skip: int = Query(default=0, ge=0),
    limit: Optional[int] = Query(default=None, ge=1),
):
    """
    获取所有提示词模板的列表。
    """
    prompts = prompt_service.get_prompts(session=session, skip=skip, limit=limit)
    return ApiResponse(data=prompts)

@router.get("/{prompt_id}", response_model=ApiResponse[PromptRead], summary="获取单个提示词")
def read_prompt(
    *,
    session: Session = Depends(get_session),
    prompt_id: int,
):
    """
    根据ID获取单个提示词模板的详细信息。
    """
    db_prompt = prompt_service.get_prompt(session=session, prompt_id=prompt_id)
    if not db_prompt:
        raise HTTPException(status_code=404, detail="提示词未找到")
    return ApiResponse(data=db_prompt)

@router.put("/{prompt_id}", response_model=ApiResponse[PromptRead], summary="更新提示词")
def update_prompt(
    *,
    session: Session = Depends(get_session),
    prompt_id: int,
    prompt: PromptUpdate,
):
    """
    更新一个已存在的提示词模板。
    """
    try:
        updated_prompt = prompt_service.update_prompt(session=session, prompt_id=prompt_id, prompt_update=prompt)
        if not updated_prompt:
            raise HTTPException(status_code=404, detail="提示词未找到")
        return ApiResponse(data=updated_prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{prompt_id}", response_model=ApiResponse, summary="删除提示词")
def delete_prompt(
    *,
    session: Session = Depends(get_session),
    prompt_id: int,
):
    """
    删除一个提示词模板。
    """
    db_prompt = prompt_service.get_prompt(session=session, prompt_id=prompt_id)
    if not db_prompt:
        raise HTTPException(status_code=404, detail="提示词未找到")
    if getattr(db_prompt, 'built_in', False):
        raise HTTPException(status_code=400, detail="系统内置提示词不可删除")
    try:
        deleted = prompt_service.delete_prompt(session=session, prompt_id=prompt_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="提示词未找到")
    return ApiResponse(message="提示词删除成功")

@router.post("/{prompt_id}/reset", response_model=ApiResponse[PromptRead], summary="重置内置提示词")
def reset_prompt_endpoint(
    *,
    session: Session = Depends(get_session),
    prompt_id: int,
):
    """
    重置内置提示词到原始状态。
    """
    try:
        result = prompt_service.reset_prompt(session=session, prompt_id=prompt_id)
        if not result:
            raise HTTPException(status_code=404, detail="提示词未找到")
        return ApiResponse(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
