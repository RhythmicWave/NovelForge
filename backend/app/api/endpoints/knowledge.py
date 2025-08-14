from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List

from app.db.session import get_session
from app.schemas.prompt import KnowledgeRead, KnowledgeCreate, KnowledgeUpdate
from app.schemas.response import ApiResponse
from app.services.knowledge_service import KnowledgeService

router = APIRouter()

@router.get('/', response_model=ApiResponse[List[KnowledgeRead]], summary='获取知识库列表')
def list_knowledge(session: Session = Depends(get_session)):
    svc = KnowledgeService(session)
    items = svc.list()
    return ApiResponse(data=items)

@router.post('/', response_model=ApiResponse[KnowledgeRead], summary='创建知识库')
def create_knowledge(body: KnowledgeCreate, session: Session = Depends(get_session)):
    svc = KnowledgeService(session)
    if svc.get_by_name(body.name):
        raise HTTPException(status_code=400, detail='同名知识库已存在')
    item = svc.create(name=body.name, description=body.description, content=body.content)
    return ApiResponse(data=item)

@router.get('/{kid}', response_model=ApiResponse[KnowledgeRead], summary='获取单个知识库')
def get_knowledge(kid: int, session: Session = Depends(get_session)):
    svc = KnowledgeService(session)
    item = svc.get_by_id(kid)
    if not item:
        raise HTTPException(status_code=404, detail='知识库不存在')
    return ApiResponse(data=item)

@router.put('/{kid}', response_model=ApiResponse[KnowledgeRead], summary='更新知识库')
def update_knowledge(kid: int, body: KnowledgeUpdate, session: Session = Depends(get_session)):
    svc = KnowledgeService(session)
    item = svc.update(kid, name=body.name, description=body.description, content=body.content)
    if not item:
        raise HTTPException(status_code=404, detail='知识库不存在')
    return ApiResponse(data=item)

@router.delete('/{kid}', response_model=ApiResponse, summary='删除知识库')
def delete_knowledge(kid: int, session: Session = Depends(get_session)):
    svc = KnowledgeService(session)
    item = svc.get_by_id(kid)
    if not item:
        raise HTTPException(status_code=404, detail='知识库不存在')
    if getattr(item, 'built_in', False):
        raise HTTPException(status_code=400, detail='系统内置知识库不可删除')
    ok = svc.delete(kid)
    if not ok:
        raise HTTPException(status_code=404, detail='知识库不存在')
    return ApiResponse(message='删除成功') 