from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List

from app.db.session import get_session
from app.schemas.project_template import (
    ProjectTemplateRead,
    ProjectTemplateCreate,
    ProjectTemplateUpdate,
)
from app.schemas.response import ApiResponse
from app.services.project_template_service import ProjectTemplateService

router = APIRouter()

@router.get('/', response_model=ApiResponse[List[ProjectTemplateRead]], summary='获取项目模板列表')
def list_templates(session: Session = Depends(get_session)):
    svc = ProjectTemplateService(session)
    items = svc.list()
    return ApiResponse(data=items)

@router.post('/', response_model=ApiResponse[ProjectTemplateRead], summary='创建项目模板')
def create_template(body: ProjectTemplateCreate, session: Session = Depends(get_session)):
    svc = ProjectTemplateService(session)
    if svc.get_by_name(body.name):
        raise HTTPException(status_code=400, detail='同名模板已存在')
    tpl = svc.create(
        name=body.name,
        description=body.description,
        items=[{
            'card_type_id': it.card_type_id,
            'display_order': it.display_order,
            'title_override': it.title_override,
        } for it in (body.items or [])]
    )
    return ApiResponse(data=tpl)

@router.get('/{tid}', response_model=ApiResponse[ProjectTemplateRead], summary='获取单个项目模板')
def get_template(tid: int, session: Session = Depends(get_session)):
    svc = ProjectTemplateService(session)
    tpl = svc.get_by_id(tid)
    if not tpl:
        raise HTTPException(status_code=404, detail='项目模板不存在')
    return ApiResponse(data=tpl)

@router.put('/{tid}', response_model=ApiResponse[ProjectTemplateRead], summary='更新项目模板')
def update_template(tid: int, body: ProjectTemplateUpdate, session: Session = Depends(get_session)):
    svc = ProjectTemplateService(session)
    tpl = svc.update(
        tid,
        name=body.name,
        description=body.description,
        items=[{
            'card_type_id': it.card_type_id,
            'display_order': it.display_order,
            'title_override': it.title_override,
        } for it in (body.items or [])] if body.items is not None else None
    )
    if not tpl:
        raise HTTPException(status_code=404, detail='项目模板不存在')
    return ApiResponse(data=tpl)

@router.delete('/{tid}', response_model=ApiResponse, summary='删除项目模板')
def delete_template(tid: int, session: Session = Depends(get_session)):
    svc = ProjectTemplateService(session)
    tpl = svc.get_by_id(tid)
    if not tpl:
        raise HTTPException(status_code=404, detail='项目模板不存在')
    if getattr(tpl, 'built_in', False):
        raise HTTPException(status_code=400, detail='系统内置项目模板不可删除')
    ok = svc.delete(tid)
    if not ok:
        raise HTTPException(status_code=404, detail='项目模板不存在')
    return ApiResponse(message='删除成功') 