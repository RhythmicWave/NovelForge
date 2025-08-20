from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Optional, List, Dict
from sqlmodel import Session, select
from loguru import logger

from app.db.session import get_session
from app.db.models import Card
from app.services.memory_service import MemoryService
from app.services.card_service import CardService
from app.schemas.entity import UpdateDynamicInfo
from app.schemas.relation_extract import RelationExtraction
from app.schemas.memory import (
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
        # 将带类型的参与者信息传递给 ingest 方法
        res = svc.ingest_relations_from_llm(
            req.project_id, 
            data, 
            volume_number=req.volume_number, 
            chapter_number=req.chapter_number,
            participants_with_type=req.participants
        )
        return IngestRelationsLLMResponse(written=res.get("written", 0))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 关系抽取或写入失败: {e}")


# === 仅抽取关系（预览用） ===
@router.post("/extract-relations-llm", response_model=RelationExtraction, summary="仅抽取实体关系（不入图）")
async def extract_relations_only(req: ExtractRelationsRequest, session: Session = Depends(get_session)):
    svc = MemoryService(session)
    try:
        # 传递参与者列表（包含类型）
        data = await svc.extract_relations_llm(req.text, req.participants, req.llm_config_id, req.timeout)
        
        # 在这里也可以选择性地进行一次后端过滤，如果需要的话
        # (代码与 ingest_relations_from_llm 中的过滤逻辑类似)

        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 关系抽取失败: {e}")

# === 仅提取动态信息（不更新） ===
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

# === 按预览后的结果入图 ===
@router.post("/ingest-relations", response_model=IngestRelationsFromPreviewResponse, summary="根据 RelationExtraction 结果入图")
def ingest_relations_from_preview(req: IngestRelationsFromPreviewRequest, session: Session = Depends(get_session)):
    svc = MemoryService(session)
    try:
        res = svc.ingest_relations_from_llm(req.project_id, req.data, volume_number=req.volume_number, chapter_number=req.chapter_number)
        return IngestRelationsFromPreviewResponse(written=res.get("written", 0))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"关系入图失败: {e}")


@router.post("/update-dynamic-info", response_model=UpdateDynamicInfoResponse)
def update_dynamic_info(req: UpdateDynamicInfoRequest, session: Session = Depends(get_session)):
    """
    接收前端预览并确认后的动态信息，执行更新。
    现在调用新的、更完整的服务函数。
    """
    svc = MemoryService(session)
    try:
        # 调用新的服务函数，它会处理删除、修改和新增
        result = svc.update_dynamic_character_info(
            project_id=req.project_id,
            data=req.data,
            queue_size=req.queue_size or 3
        )
        return UpdateDynamicInfoResponse(
            success=result.get("success", False),
            updated_card_count=result.get("updated_card_count", 0)
        )
    except Exception as e:
        logger.error(f"Failed to update dynamic info: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 