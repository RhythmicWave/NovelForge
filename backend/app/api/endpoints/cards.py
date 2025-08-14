from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List

from app.db.session import get_session
from app.services.card_service import CardService, CardTypeService
from app.schemas.card import CardRead, CardCreate, CardUpdate, CardTypeRead, CardTypeCreate, CardTypeUpdate
from app.db.models import Card, CardType
# from app.services.memory_service import MemoryService
from loguru import logger

router = APIRouter()

# --- CardType Endpoints ---
# 说明：CardTypeRead 需包含 default_ai_context_template 字段（由 Pydantic schema 定义控制）。

@router.post("/card-types", response_model=CardTypeRead)
def create_card_type(card_type: CardTypeCreate, db: Session = Depends(get_session)):
    service = CardTypeService(db)
    return service.create(card_type)

@router.get("/card-types", response_model=List[CardTypeRead])
def get_all_card_types(db: Session = Depends(get_session)):
    service = CardTypeService(db)
    return service.get_all()

@router.get("/card-types/{card_type_id}", response_model=CardTypeRead)
def get_card_type(card_type_id: int, db: Session = Depends(get_session)):
    service = CardTypeService(db)
    db_card_type = service.get_by_id(card_type_id)
    if db_card_type is None:
        raise HTTPException(status_code=404, detail="CardType not found")
    return db_card_type

@router.put("/card-types/{card_type_id}", response_model=CardTypeRead)
def update_card_type(card_type_id: int, card_type: CardTypeUpdate, db: Session = Depends(get_session)):
    service = CardTypeService(db)
    db_card_type = service.update(card_type_id, card_type)
    if db_card_type is None:
        raise HTTPException(status_code=404, detail="CardType not found")
    return db_card_type

@router.delete("/card-types/{card_type_id}", status_code=204)
def delete_card_type(card_type_id: int, db: Session = Depends(get_session)):
    service = CardTypeService(db)
    db_card_type = service.get_by_id(card_type_id)
    if not db_card_type:
        raise HTTPException(status_code=404, detail="CardType not found")
    if getattr(db_card_type, 'built_in', False):
        raise HTTPException(status_code=400, detail="系统内置卡片类型不可删除")
    if not service.delete(card_type_id):
        raise HTTPException(status_code=404, detail="CardType not found")
    return {"ok": True}

# --- Card Endpoints ---

@router.post("/projects/{project_id}/cards", response_model=CardRead)
def create_card_for_project(project_id: int, card: CardCreate, db: Session = Depends(get_session)):
    service = CardService(db)
    created = service.create(card, project_id)
    # 入图（创建时）
    # 新方案：创建/更新卡片不再自动入图
    return created

@router.get("/projects/{project_id}/cards", response_model=List[CardRead])
def get_all_cards_for_project(project_id: int, db: Session = Depends(get_session)):
    service = CardService(db)
    return service.get_all_for_project(project_id)

@router.get("/cards/{card_id}", response_model=CardRead)
def get_card(card_id: int, db: Session = Depends(get_session)):
    service = CardService(db)
    db_card = service.get_by_id(card_id)
    if db_card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return db_card

@router.put("/cards/{card_id}", response_model=CardRead)
def update_card(card_id: int, card: CardUpdate, db: Session = Depends(get_session)):
    service = CardService(db)
    db_card = service.update(card_id, card)
    if db_card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    # 新方案：创建/更新卡片不再自动入图
    return db_card

@router.delete("/cards/{card_id}", status_code=204)
def delete_card(card_id: int, db: Session = Depends(get_session)):
    service = CardService(db)
    if not service.delete(card_id):
        raise HTTPException(status_code=404, detail="Card not found")
    return {"ok": True} 