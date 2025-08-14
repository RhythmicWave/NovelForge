from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from typing import Any
from sqlmodel import Session, select

from app.db.session import get_session
from app.db.models import Card
from app.services.memory_service import MemoryService
from app.services.card_service import CardService
from app.schemas.entity import UpdateDynamicInfo
from app.schemas.relation_extract import RelationExtraction
from app.schemas.memory import (
    IngestCardTextRequest,
    QueryRequest,
    QueryResponse,
    IngestRelationsLLMRequest,
    IngestRelationsLLMResponse,
    ExtractRelationsRequest,
    IngestRelationsFromPreviewRequest,
    IngestRelationsFromPreviewResponse,
    ExtractOnlyRequest,
    UpdateDynamicInfoRequest,
    UpdateDynamicInfoResponse,
)


router = APIRouter()


@router.post("/ingest-card-text")
def ingest_card_text(body: IngestCardTextRequest, session: Session = Depends(get_session)):
    # 该端点已废弃 Episode 写入，仅保持兼容返回成功。
    card: Card | None = session.get(Card, body.card_id)
    if card is None or card.project_id != body.project_id:
        raise HTTPException(status_code=404, detail="卡片不存在或不属于该项目")
    return {"success": True, "card_id": body.card_id}


@router.post("/query", response_model=QueryResponse, summary="检索子图/快照")
def query(req: QueryRequest, session: Session = Depends(get_session)):
    svc = MemoryService(session)
    data = svc.graph.query_subgraph(project_id=req.project_id, participants=req.participants, radius=req.radius)
    return QueryResponse(**data)


@router.post("/ingest-relations-llm", response_model=IngestRelationsLLMResponse, summary="使用 LLM 抽取实体关系并入图（严格）")
async def ingest_relations_llm(req: IngestRelationsLLMRequest, session: Session = Depends(get_session)):
    svc = MemoryService(session)
    try:
        data = await svc.extract_relations_llm(req.text, req.participants, req.llm_config_id, req.timeout)
        res = svc.ingest_relations_from_llm(req.project_id, data, volume_number=req.volume_number, chapter_number=req.chapter_number)
        return IngestRelationsLLMResponse(written=res.get("written", 0))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 关系抽取或写入失败: {e}")


# === 新增：仅抽取关系（预览用） ===
@router.post("/extract-relations-llm", response_model=RelationExtraction, summary="仅抽取实体关系（不入图）")
async def extract_relations_only(req: ExtractRelationsRequest, session: Session = Depends(get_session)):
    svc = MemoryService(session)
    try:
        data = await svc.extract_relations_llm(req.text, req.participants, req.llm_config_id, req.timeout)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 关系抽取失败: {e}")

# === 恢复：仅提取动态信息（不更新） ===
@router.post("/extract-dynamic-info", response_model=UpdateDynamicInfo, summary="仅提取动态信息（不更新）")
async def extract_dynamic_info_only(req: ExtractOnlyRequest, session: Session = Depends(get_session)):
    svc = MemoryService(session)
    try:
        data = await svc.extract_dynamic_info_from_text(
            text=req.text,
            participants=req.participants,
            llm_config_id=req.llm_config_id,
            timeout=req.timeout,
            project_id=req.project_id,
            extra_context=req.extra_context,
        )
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"动态信息提取失败: {e}")

# === 新增：按预览后的结果入图 ===
@router.post("/ingest-relations", response_model=IngestRelationsFromPreviewResponse, summary="根据 RelationExtraction 结果入图")
def ingest_relations_from_preview(req: IngestRelationsFromPreviewRequest, session: Session = Depends(get_session)):
    svc = MemoryService(session)
    try:
        res = svc.ingest_relations_from_llm(req.project_id, req.data, volume_number=req.volume_number, chapter_number=req.chapter_number)
        return IngestRelationsFromPreviewResponse(written=res.get("written", 0))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"关系入图失败: {e}")


@router.post("/update-dynamic-info", response_model=UpdateDynamicInfoResponse, summary="仅更新动态信息到角色卡")
def update_dynamic_info_only(req: UpdateDynamicInfoRequest, session: Session = Depends(get_session)):
    card_svc = CardService(session)
    try:
        updated_cards = card_svc.update_character_dynamic_info(
            project_id=req.project_id,
            update_data=req.data,
            queue_size=req.queue_size or 5,
        )
        return UpdateDynamicInfoResponse(success=True, updated_card_count=len(updated_cards))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"动态信息更新失败: {e}") 