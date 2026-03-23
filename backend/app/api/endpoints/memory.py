from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.entity import UpdateDynamicInfo
from app.schemas.memory import (
	ApplyPreviewRequest,
	ApplyPreviewResponse,
	ExtractOnlyRequest,
	ExtractPreviewRequest,
	ExtractPreviewResponse,
	ExtractRelationsRequest,
	IngestRelationsFromPreviewRequest,
	IngestRelationsFromPreviewResponse,
	IngestRelationsLLMRequest,
	IngestRelationsLLMResponse,
	MemoryExtractorListResponse,
	QueryRequest,
	QueryResponse,
	UpdateDynamicInfoRequest,
	UpdateDynamicInfoResponse,
)
from app.schemas.relation_extract import RelationExtraction
from app.services.memory_service import MemoryService


router = APIRouter()


@router.get("/extractors", response_model=MemoryExtractorListResponse, summary="获取可用记忆抽取器列表")
def list_extractors(session: Session = Depends(get_session)):
	svc = MemoryService(session)
	return MemoryExtractorListResponse(items=svc.list_extractors())


@router.post("/extract-preview", response_model=ExtractPreviewResponse, summary="通用记忆提取预览")
async def extract_preview(req: ExtractPreviewRequest, session: Session = Depends(get_session)):
	svc = MemoryService(session)
	try:
		result = await svc.extract_preview(
			extractor_code=req.extractor_code,
			project_id=req.project_id,
			text=req.text,
			participants=req.participants,
			llm_config_id=req.llm_config_id,
			temperature=req.temperature,
			max_tokens=req.max_tokens,
			timeout=req.timeout,
			extra_context=req.extra_context,
			volume_number=req.volume_number,
			chapter_number=req.chapter_number,
		)
		return ExtractPreviewResponse(**result)
	except KeyError:
		raise HTTPException(status_code=404, detail=f"未知抽取器: {req.extractor_code}")
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"记忆提取预览失败: {e}")


@router.post("/apply-preview", response_model=ApplyPreviewResponse, summary="通用记忆提取确认写入")
def apply_preview(req: ApplyPreviewRequest, session: Session = Depends(get_session)):
	svc = MemoryService(session)
	try:
		result = svc.apply_preview(
			extractor_code=req.extractor_code,
			project_id=req.project_id,
			data=req.data,
			options=req.options,
			volume_number=req.volume_number,
			chapter_number=req.chapter_number,
			participants=req.participants,
		)
		return ApplyPreviewResponse(**result)
	except KeyError:
		raise HTTPException(status_code=404, detail=f"未知抽取器: {req.extractor_code}")
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"记忆写入失败: {e}")


@router.post("/query", response_model=QueryResponse, summary="检索子图快照")
def query(req: QueryRequest, session: Session = Depends(get_session)):
	svc = MemoryService(session)
	data = svc.graph.query_subgraph(project_id=req.project_id, participants=req.participants, radius=req.radius)
	return QueryResponse(**data)


@router.post("/ingest-relations-llm", response_model=IngestRelationsLLMResponse, summary="使用 LLM 抽取关系并写入图谱")
async def ingest_relations_llm(req: IngestRelationsLLMRequest, session: Session = Depends(get_session)):
	svc = MemoryService(session)
	try:
		preview = await svc.extract_preview(
			extractor_code="relation",
			project_id=req.project_id,
			text=req.text,
			participants=req.participants,
			llm_config_id=req.llm_config_id,
			temperature=req.temperature,
			max_tokens=req.max_tokens,
			timeout=req.timeout,
			volume_number=req.volume_number,
			chapter_number=req.chapter_number,
		)
		res = svc.apply_preview(
			extractor_code="relation",
			project_id=req.project_id,
			data=preview["preview_data"],
			volume_number=req.volume_number,
			chapter_number=req.chapter_number,
			participants=req.participants,
		)
		return IngestRelationsLLMResponse(written=res.get("written", 0))
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"LLM 关系抽取或写入失败: {e}")


@router.post("/extract-relations-llm", response_model=RelationExtraction, summary="仅抽取实体关系（不入图）")
async def extract_relations_only(req: ExtractRelationsRequest, session: Session = Depends(get_session)):
	svc = MemoryService(session)
	try:
		result = await svc.extract_preview(
			extractor_code="relation",
			project_id=None,
			text=req.text,
			participants=req.participants,
			llm_config_id=req.llm_config_id,
			temperature=req.temperature,
			max_tokens=req.max_tokens,
			timeout=req.timeout,
			volume_number=req.volume_number,
			chapter_number=req.chapter_number,
		)
		return RelationExtraction.model_validate(result["preview_data"])
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"LLM 关系抽取失败: {e}")


@router.post("/extract-dynamic-info", response_model=UpdateDynamicInfo, summary="仅提取角色动态信息（不更新）")
async def extract_dynamic_info_only(req: ExtractOnlyRequest, session: Session = Depends(get_session)):
	svc = MemoryService(session)
	try:
		result = await svc.extract_preview(
			extractor_code="character_dynamic",
			project_id=req.project_id,
			text=req.text,
			participants=req.participants,
			llm_config_id=req.llm_config_id,
			temperature=req.temperature,
			max_tokens=req.max_tokens,
			timeout=req.timeout,
			extra_context=req.extra_context,
		)
		return UpdateDynamicInfo.model_validate(result["preview_data"])
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"动态信息提取失败: {e}")


@router.post("/ingest-relations", response_model=IngestRelationsFromPreviewResponse, summary="根据 RelationExtraction 结果入图")
def ingest_relations_from_preview(req: IngestRelationsFromPreviewRequest, session: Session = Depends(get_session)):
	svc = MemoryService(session)
	try:
		res = svc.apply_preview(
			extractor_code="relation",
			project_id=req.project_id,
			data=req.data.model_dump(mode="json"),
			volume_number=req.volume_number,
			chapter_number=req.chapter_number,
		)
		return IngestRelationsFromPreviewResponse(written=res.get("written", 0))
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"关系入图失败: {e}")


@router.post("/update-dynamic-info", response_model=UpdateDynamicInfoResponse, summary="根据预览结果写入角色动态信息")
def update_dynamic_info(req: UpdateDynamicInfoRequest, session: Session = Depends(get_session)):
	svc = MemoryService(session)
	try:
		result = svc.apply_preview(
			extractor_code="character_dynamic",
			project_id=req.project_id,
			data=req.data.model_dump(mode="json"),
			options={"queue_size": req.queue_size or 3},
		)
		return UpdateDynamicInfoResponse(
			success=result.get("success", False),
			updated_card_count=result.get("updated_card_count", 0),
		)
	except Exception as e:
		logger.error(f"Failed to update dynamic info: {e}")
		raise HTTPException(status_code=500, detail=str(e))
