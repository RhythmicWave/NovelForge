from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List, Dict, Any
from urllib.parse import quote

from app.db.session import get_session
from app.services.card_service import CardService, CardTypeService
from app.services.card_export_service import CardExportService
from app.services.schema_service import compose_schema_with_card_types, localize_schema_titles
from app.services.card_params_service import merge_effective_ai_params
from app.schemas.card import (
    CardRead, CardCreate, CardUpdate, 
    CardTypeRead, CardTypeCreate, CardTypeUpdate,
    CardBatchReorderRequest,
    CardExportRequest,
)
from app.db.models import Card, CardType
from app.exceptions import BusinessException
from loguru import logger

from app.schemas.card import CardCopyOrMoveRequest
from app.core import emit_event
from fastapi import Response

router = APIRouter()


def _resolve_card_type_name(db: Session, card: Card) -> str | None:
    """Resolve card type name for event payloads reliably."""
    card_type = getattr(card, "card_type", None)
    if card_type and getattr(card_type, "name", None):
        return str(card_type.name)

    card_type_id = getattr(card, "card_type_id", None)
    if not card_type_id:
        return None

    db_card_type = db.get(CardType, card_type_id)
    if db_card_type and getattr(db_card_type, "name", None):
        return str(db_card_type.name)
    return None

# --- CardType Endpoints ---
# 说明：CardTypeRead 需包含 default_ai_context_template 字段（由 Pydantic schema 定义控制）。

@router.post("/card-types", response_model=CardTypeRead)
def create_card_type(card_type: CardTypeCreate, db: Session = Depends(get_session)):
    service = CardTypeService(db)
    created = service.create(card_type)
    data = created.model_dump()
    data["json_schema"] = localize_schema_titles(data.get("json_schema"))
    return data

@router.get("/card-types", response_model=List[CardTypeRead])
def get_all_card_types(db: Session = Depends(get_session)):
    service = CardTypeService(db)
    result = []
    for card_type in service.get_all():
        data = card_type.model_dump()
        data["json_schema"] = localize_schema_titles(data.get("json_schema"))
        result.append(data)
    return result

@router.get("/card-types/{card_type_id}", response_model=CardTypeRead)
def get_card_type(card_type_id: int, db: Session = Depends(get_session)):
    service = CardTypeService(db)
    db_card_type = service.get_by_id(card_type_id)
    if db_card_type is None:
        raise HTTPException(status_code=404, detail="CardType not found")
    data = db_card_type.model_dump()
    data["json_schema"] = localize_schema_titles(data.get("json_schema"))
    return data

@router.put("/card-types/{card_type_id}", response_model=CardTypeRead)
def update_card_type(card_type_id: int, card_type: CardTypeUpdate, db: Session = Depends(get_session)):
    service = CardTypeService(db)
    db_card_type = service.update(card_type_id, card_type)
    if db_card_type is None:
        raise HTTPException(status_code=404, detail="CardType not found")
    data = db_card_type.model_dump()
    data["json_schema"] = localize_schema_titles(data.get("json_schema"))
    return data

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

# --- CardType Schema Endpoints ---

@router.get("/card-types/{card_type_id}/schema")
def get_card_type_schema(card_type_id: int, db: Session = Depends(get_session)) -> Dict[str, Any]:
    ct = db.get(CardType, card_type_id)
    if not ct:
        raise HTTPException(status_code=404, detail="CardType not found")
    localized_schema = localize_schema_titles(ct.json_schema) if isinstance(ct.json_schema, dict) else ct.json_schema
    return {"json_schema": localized_schema}

@router.put("/card-types/{card_type_id}/schema")
def update_card_type_schema(card_type_id: int, payload: Dict[str, Any], db: Session = Depends(get_session)) -> Dict[str, Any]:
    ct = db.get(CardType, card_type_id)
    if not ct:
        raise HTTPException(status_code=404, detail="CardType not found")
    ct.json_schema = payload.get("json_schema")
    db.add(ct)
    db.commit()
    db.refresh(ct)
    localized_schema = localize_schema_titles(ct.json_schema) if isinstance(ct.json_schema, dict) else ct.json_schema
    return {"json_schema": localized_schema}

# --- CardType AI Params Endpoints ---

@router.get("/card-types/{card_type_id}/ai-params")
def get_card_type_ai_params(card_type_id: int, db: Session = Depends(get_session)) -> Dict[str, Any]:
    ct = db.get(CardType, card_type_id)
    if not ct:
        raise HTTPException(status_code=404, detail="CardType not found")
    return {"ai_params": getattr(ct, 'ai_params', None)}

@router.put("/card-types/{card_type_id}/ai-params")
def update_card_type_ai_params(card_type_id: int, payload: Dict[str, Any], db: Session = Depends(get_session)) -> Dict[str, Any]:
    ct = db.get(CardType, card_type_id)
    if not ct:
        raise HTTPException(status_code=404, detail="CardType not found")
    ct.ai_params = payload.get("ai_params")
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return {"ai_params": ct.ai_params}

# --- Card Endpoints ---

@router.post("/projects/{project_id}/cards", response_model=CardRead)
def create_card_for_project(project_id: int, card: CardCreate, db: Session = Depends(get_session)):
    service = CardService(db)
    try:
        created = service.create(card, project_id)
        triggered_run_ids = []
        try:
            event_data = {
                "session": db,
                "card": created,
                "is_created": True,
                "card_type": _resolve_card_type_name(db, created),
            }
            emit_event("card.saved", event_data)
            triggered_run_ids = event_data.get("triggered_run_ids", [])
        except Exception:
            logger.exception("OnSave workflow trigger failed")
        
        # Header is managed by Middleware
        
        return created
    except BusinessException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

@router.get("/projects/{project_id}/cards", response_model=List[CardRead])
def get_all_cards_for_project(project_id: int, db: Session = Depends(get_session)):
    service = CardService(db)
    return service.get_all_for_project(project_id)


@router.post("/projects/{project_id}/cards/export")
def export_cards_for_project(project_id: int, payload: CardExportRequest, db: Session = Depends(get_session)):
    service = CardExportService(db)
    try:
        exported = service.export(project_id=project_id, request=payload)
        disposition = f"attachment; filename*=UTF-8''{quote(exported.filename)}"
        return Response(
            content=exported.content,
            media_type=exported.media_type,
            headers={"Content-Disposition": disposition},
        )
    except BusinessException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

@router.get("/cards/{card_id}", response_model=CardRead)
def get_card(card_id: int, db: Session = Depends(get_session)):
    service = CardService(db)
    db_card = service.get_by_id(card_id)
    if db_card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return db_card

@router.put("/cards/{card_id}", response_model=CardRead)
def update_card(card_id: int, card: CardUpdate, db: Session = Depends(get_session)):
    # 获取更新前的状态
    old_card = db.get(Card, card_id)
    old_content = None
    if old_card and old_card.content:
        import copy
        old_content = copy.deepcopy(old_card.content)

    was_needs_confirmation = getattr(old_card, 'needs_confirmation', False) if old_card else False
    
    service = CardService(db)
    db_card = service.update(card_id, card)
    if db_card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    
    # 检查是否从"需要确认"状态变为"已确认"状态
    is_now_confirmed = was_needs_confirmation and not getattr(db_card, 'needs_confirmation', False)
    
    # 用户保存时的处理
    if is_now_confirmed:
        # 场景1：用户确认了 AI 修改的卡片
        logger.info(f"✅ 用户确认了 AI 修改的卡片 {card_id}，准备触发工作流")
        db_card.last_modified_by = "user"
        db_card.ai_modified = False  # 清除 AI 修改标记
        db.add(db_card)
        db.commit()
        db.refresh(db_card)
    elif not was_needs_confirmation and getattr(db_card, 'last_modified_by', None) != 'user':
        # 场景2：用户手动修改卡片（非 AI 创建的，或已确认过的）
        # 标记为用户修改，但不影响工作流触发
        db_card.last_modified_by = "user"
        db.add(db_card)
        db.commit()
        db.refresh(db_card)
    
    triggered_run_ids = []
    try:
        event_data = {
            "session": db, 
            "card": db_card, 
            "is_created": False,
            "old_content": old_content,
            "card_type": _resolve_card_type_name(db, db_card),
        }
        emit_event("card.saved", event_data)
        triggered_run_ids = event_data.get("triggered_run_ids", [])
        
        if is_now_confirmed and triggered_run_ids:
            logger.info(f"🎯 AI修改卡片确认后触发了 {len(triggered_run_ids)} 个工作流")
    except Exception:
        logger.exception("OnSave workflow trigger failed")
    
    # Header is managed by Middleware
    
    return db_card


@router.post("/cards/batch-reorder")
def batch_reorder_cards(request: CardBatchReorderRequest, db: Session = Depends(get_session)):
    """
    批量更新卡片排序
    
    Args:
        request: 包含要更新的卡片列表，每个卡片包含 card_id, display_order, parent_id
        
    Returns:
        更新的卡片数量和成功状态
    """
    try:
        updated_count = 0
        
        # 批量更新所有卡片
        for item in request.updates:
            card = db.get(Card, item.card_id)
            if card:
                # 更新 display_order
                card.display_order = item.display_order
                
                # 更新 parent_id（无论是否变化都更新，因为前端已经明确传递了值）
                # 这样可以正确处理：设置为根级(null)、设置为子卡片(有值)、保持不变(传递当前值)
                card.parent_id = item.parent_id
                    
                db.add(card)
                updated_count += 1
        
        # 一次性提交所有更新
        db.commit()
        
        logger.info(f"批量更新排序完成，共更新 {updated_count} 张卡片")
        
        return {
            "success": True,
            "updated_count": updated_count,
            "message": f"成功更新 {updated_count} 张卡片的排序"
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"批量更新排序失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量更新失败: {str(e)}")


@router.delete("/cards/{card_id}", status_code=204)
def delete_card(card_id: int, db: Session = Depends(get_session)):
    service = CardService(db)
    if not service.delete(card_id):
        raise HTTPException(status_code=404, detail="Card not found")
    return {"ok": True}

@router.post("/cards/{card_id}/copy", response_model=CardRead)
def copy_card_endpoint(card_id: int, payload: CardCopyOrMoveRequest, db: Session = Depends(get_session)):
    service = CardService(db)
    try:
        copied = service.copy_card(card_id, payload.target_project_id, payload.parent_id)
        if not copied:
            raise HTTPException(status_code=404, detail="Card not found")
        return copied
    except BusinessException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

@router.post("/cards/{card_id}/move", response_model=CardRead)
def move_card_endpoint(card_id: int, payload: CardCopyOrMoveRequest, db: Session = Depends(get_session)):
    service = CardService(db)
    try:
        moved = service.move_card(card_id, payload.target_project_id, payload.parent_id)
        if not moved:
            raise HTTPException(status_code=404, detail="Card not found")
        return moved
    except BusinessException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) 

# --- Card Schema Endpoints ---

@router.get("/cards/{card_id}/schema")
def get_card_schema(card_id: int, db: Session = Depends(get_session)) -> Dict[str, Any]:
    c = db.get(Card, card_id)
    if not c:
        raise HTTPException(status_code=404, detail="Card not found")
    effective = c.json_schema if c.json_schema is not None else (c.card_type.json_schema if c.card_type else None)
    # 动态装配引用
    composed = compose_schema_with_card_types(db, effective or {})
    return {"json_schema": c.json_schema, "effective_schema": composed, "follow_type": c.json_schema is None}

@router.put("/cards/{card_id}/schema")
def update_card_schema(card_id: int, payload: Dict[str, Any], db: Session = Depends(get_session)) -> Dict[str, Any]:
    c = db.get(Card, card_id)
    if not c:
        raise HTTPException(status_code=404, detail="Card not found")
    # 传入 null/None 表示恢复跟随类型
    c.json_schema = payload.get("json_schema", None)
    db.add(c)
    db.commit()
    db.refresh(c)
    effective = c.json_schema if c.json_schema is not None else (c.card_type.json_schema if c.card_type else None)
    composed = compose_schema_with_card_types(db, effective or {})
    return {"json_schema": c.json_schema, "effective_schema": composed, "follow_type": c.json_schema is None}

@router.post("/cards/{card_id}/schema/apply-to-type")
def apply_card_schema_to_type(card_id: int, db: Session = Depends(get_session)) -> Dict[str, Any]:
    c = db.get(Card, card_id)
    if not c:
        raise HTTPException(status_code=404, detail="Card not found")
    if not c.card_type:
        raise HTTPException(status_code=400, detail="Card has no type")
    # 取实例 schema；若为空则取有效 schema
    effective = c.json_schema if c.json_schema is not None else (c.card_type.json_schema or None)
    if effective is None:
        raise HTTPException(status_code=400, detail="No schema to apply")
    c.card_type.json_schema = effective
    db.add(c.card_type)
    db.commit()
    db.refresh(c.card_type)
    return {"json_schema": c.card_type.json_schema} 

# --- Card AI Params Endpoints ---

@router.get("/cards/{card_id}/ai-params")
def get_card_ai_params(card_id: int, db: Session = Depends(get_session)) -> Dict[str, Any]:
    c = db.get(Card, card_id)
    if not c:
        raise HTTPException(status_code=404, detail="Card not found")
    effective = merge_effective_ai_params(db, c)
    return {"ai_params": c.ai_params, "effective_params": effective, "follow_type": c.ai_params is None}

@router.put("/cards/{card_id}/ai-params")
def update_card_ai_params(card_id: int, payload: Dict[str, Any], db: Session = Depends(get_session)) -> Dict[str, Any]:
    c = db.get(Card, card_id)
    if not c:
        raise HTTPException(status_code=404, detail="Card not found")
    c.ai_params = payload.get("ai_params", None)
    db.add(c)
    db.commit()
    db.refresh(c)
    effective = merge_effective_ai_params(db, c)
    return {"ai_params": c.ai_params, "effective_params": effective, "follow_type": c.ai_params is None}

@router.post("/cards/{card_id}/ai-params/apply-to-type")
def apply_card_ai_params_to_type(card_id: int, db: Session = Depends(get_session)) -> Dict[str, Any]:
    c = db.get(Card, card_id)
    if not c:
        raise HTTPException(status_code=404, detail="Card not found")
    effective = merge_effective_ai_params(db, c)
    if not effective:
        raise HTTPException(status_code=400, detail="No ai_params to apply")
    if not c.card_type:
        raise HTTPException(status_code=400, detail="Card has no type")
    c.card_type.ai_params = effective
    db.add(c.card_type)
    db.commit()
    db.refresh(c.card_type)
    return {"ai_params": c.card_type.ai_params} 
