from fastapi import APIRouter, Depends, HTTPException
from typing import List
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
    new_prompt = prompt_service.create_prompt(session=session, prompt_create=prompt)
    return ApiResponse(data=new_prompt)

@router.get("/", response_model=ApiResponse[List[PromptRead]], summary="获取提示词列表")
def read_prompts(
    *,
    session: Session = Depends(get_session),
    skip: int = 0,
    limit: int = 100,
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
    updated_prompt = prompt_service.update_prompt(session=session, prompt_id=prompt_id, prompt_update=prompt)
    if not updated_prompt:
        raise HTTPException(status_code=404, detail="提示词未找到")
    return ApiResponse(data=updated_prompt)

@router.delete("/{prompt_id}", response_model=ApiResponse, summary="删除提示词")
def delete_prompt(
    *,
    session: Session = Depends(get_session),
    prompt_id: int,
):
    """
    删除一个提示词模板。
    """
    if not prompt_service.delete_prompt(session=session, prompt_id=prompt_id):
        raise HTTPException(status_code=404, detail="提示词未找到")
    return ApiResponse(message="提示词删除成功") 