from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List, Dict, Any

from app.db.session import get_session
from app.services.card_service import CardService, CardTypeService
from app.schemas.card import CardRead, CardCreate, CardUpdate, CardTypeRead, CardTypeCreate, CardTypeUpdate
from app.db.models import Card, CardType, LLMConfig
from loguru import logger

from app.schemas.card import CardCopyOrMoveRequest
from app.services.workflow_triggers import trigger_on_card_save
from fastapi import Response

router = APIRouter()

# --- helpers ---
def _collect_ref_names(node: Any, refs: set):
    if isinstance(node, dict):
        if '$ref' in node and isinstance(node['$ref'], str) and node['$ref'].startswith('#/$defs/'):
            name = node['$ref'].split('/')[-1]
            if name:
                refs.add(name)
        for v in node.values():
            _collect_ref_names(v, refs)
    elif isinstance(node, list):
        for v in node:
            _collect_ref_names(v, refs)

def _compose_schema_with_types(schema: dict, db: Session) -> dict:
    if not isinstance(schema, dict):
        return schema
    result = dict(schema)
    if '$defs' not in result or not isinstance(result.get('$defs'), dict):
        result['$defs'] = {}
    existing_defs = result['$defs']
    ref_names: set = set()
    _collect_ref_names(result, ref_names)
    # 查询所有类型一次，建立 name/model_name -> schema 映射
    all_types = db.query(CardType).all()
    by_model = {}
    for ct in all_types:
        if ct and ct.json_schema:
            if ct.model_name:
                by_model[ct.model_name] = ct.json_schema
            by_model[ct.name] = ct.json_schema
    # 覆盖策略：对所有被引用的名称，若 CardType 有对应结构，则覆盖/写入到 $defs
    for n in ref_names:
        sch = by_model.get(n)
        if sch:
            existing_defs[n] = sch
    result['$defs'] = existing_defs
    return result

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

# --- CardType Schema Endpoints ---

@router.get("/card-types/{card_type_id}/schema")
def get_card_type_schema(card_type_id: int, db: Session = Depends(get_session)) -> Dict[str, Any]:
    ct = db.get(CardType, card_type_id)
    if not ct:
        raise HTTPException(status_code=404, detail="CardType not found")
    return {"json_schema": ct.json_schema}

@router.put("/card-types/{card_type_id}/schema")
def update_card_type_schema(card_type_id: int, payload: Dict[str, Any], db: Session = Depends(get_session)) -> Dict[str, Any]:
    ct = db.get(CardType, card_type_id)
    if not ct:
        raise HTTPException(status_code=404, detail="CardType not found")
    ct.json_schema = payload.get("json_schema")
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return {"json_schema": ct.json_schema}

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
def create_card_for_project(project_id: int, card: CardCreate, db: Session = Depends(get_session), response: Response = None):
    service = CardService(db)
    created = service.create(card, project_id)
    try:
        run_ids = trigger_on_card_save(db, created)
        if response is not None and run_ids:
            response.headers["X-Workflows-Started"] = ",".join(str(r) for r in run_ids)
    except Exception:
        logger.exception("OnSave workflow trigger failed")
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
def update_card(card_id: int, card: CardUpdate, db: Session = Depends(get_session), response: Response = None):
    service = CardService(db)
    db_card = service.update(card_id, card)
    if db_card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    try:
        run_ids = trigger_on_card_save(db, db_card)
        if response is not None and run_ids:
            response.headers["X-Workflows-Started"] = ",".join(str(r) for r in run_ids)
    except Exception:
        logger.exception("OnSave workflow trigger failed")
    return db_card

@router.delete("/cards/{card_id}", status_code=204)
def delete_card(card_id: int, db: Session = Depends(get_session)):
    service = CardService(db)
    if not service.delete(card_id):
        raise HTTPException(status_code=404, detail="Card not found")
    return {"ok": True}

@router.post("/cards/{card_id}/copy", response_model=CardRead)
def copy_card_endpoint(card_id: int, payload: CardCopyOrMoveRequest, db: Session = Depends(get_session)):
    service = CardService(db)
    copied = service.copy_card(card_id, payload.target_project_id, payload.parent_id)
    if not copied:
        raise HTTPException(status_code=404, detail="Card not found")
    return copied

@router.post("/cards/{card_id}/move", response_model=CardRead)
def move_card_endpoint(card_id: int, payload: CardCopyOrMoveRequest, db: Session = Depends(get_session)):
    service = CardService(db)
    moved = service.move_card(card_id, payload.target_project_id, payload.parent_id)
    if not moved:
        raise HTTPException(status_code=404, detail="Card not found")
    return moved 

# --- Card Schema Endpoints ---

@router.get("/cards/{card_id}/schema")
def get_card_schema(card_id: int, db: Session = Depends(get_session)) -> Dict[str, Any]:
    c = db.get(Card, card_id)
    if not c:
        raise HTTPException(status_code=404, detail="Card not found")
    effective = c.json_schema if c.json_schema is not None else (c.card_type.json_schema if c.card_type else None)
    # 动态装配引用
    composed = _compose_schema_with_types(effective or {}, db)
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
    composed = _compose_schema_with_types(effective or {}, db)
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

def _merge_effective_params(db: Session, card: Card) -> Dict[str, Any]:
    base = (card.card_type.ai_params if card.card_type and card.card_type.ai_params else {}) or {}
    override = (card.ai_params or {})
    eff = { **base, **override }
    # 补齐字段结构（五项）：llm_config_id/prompt_name/temperature/max_tokens/timeout
    if eff.get("llm_config_id") in (None, 0, "0", ""):
        # 选用一个默认 LLM（id 最小）
        try:
            llm = db.query(LLMConfig).order_by(LLMConfig.id.asc()).first()  # type: ignore
            if llm:
                eff["llm_config_id"] = int(getattr(llm, "id", 0))
        except Exception:
            pass
    # 规范类型
    if eff.get("llm_config_id") is not None:
        try: eff["llm_config_id"] = int(eff.get("llm_config_id"))
        except Exception: pass
    return eff

@router.get("/cards/{card_id}/ai-params")
def get_card_ai_params(card_id: int, db: Session = Depends(get_session)) -> Dict[str, Any]:
    c = db.get(Card, card_id)
    if not c:
        raise HTTPException(status_code=404, detail="Card not found")
    effective = _merge_effective_params(db, c)
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
    effective = _merge_effective_params(db, c)
    return {"ai_params": c.ai_params, "effective_params": effective, "follow_type": c.ai_params is None}

@router.post("/cards/{card_id}/ai-params/apply-to-type")
def apply_card_ai_params_to_type(card_id: int, db: Session = Depends(get_session)) -> Dict[str, Any]:
    c = db.get(Card, card_id)
    if not c:
        raise HTTPException(status_code=404, detail="Card not found")
    effective = _merge_effective_params(db, c)
    if not effective:
        raise HTTPException(status_code=400, detail="No ai_params to apply")
    if not c.card_type:
        raise HTTPException(status_code=400, detail="Card has no type")
    c.card_type.ai_params = effective
    db.add(c.card_type)
    db.commit()
    db.refresh(c.card_type)
    return {"ai_params": c.card_type.ai_params} 