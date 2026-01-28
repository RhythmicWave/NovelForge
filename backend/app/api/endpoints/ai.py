from fastapi import APIRouter, Depends, HTTPException, Body
from sqlmodel import Session
from app.db.session import get_session
from app.schemas.ai import ContinuationRequest, ContinuationResponse, GeneralAIRequest
from app.schemas.response import ApiResponse
from app.services import prompt_service, llm_config_service

from app.services.schema_service import compose_full_schema
from app.utils.stream_utils import wrap_sse_stream
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from typing import Type, Dict, Any, List
import json

from app.db.models import Card, CardType
from app.utils.schema_utils import filter_schema_for_ai

# 引入知识库
from app.services.knowledge_service import KnowledgeService
import re
from app.schemas.entity import DYNAMIC_INFO_TYPES
from app.schemas import entity as entity_schemas
from app.core import emit_event
from app.services.context_service import assemble_context, ContextAssembleParams
from app.services.ai.core import llm_service
from app.services.ai.core.model_builder import build_model_from_json_schema
from app.services.ai.generation.instruction_validator import validate_instruction, apply_instruction
from app.services.ai.generation.instruction_generator import generate_instruction_stream
from app.services.ai.generation.prompt_builder import build_instruction_system_prompt
from app.schemas.instruction import InstructionGenerateRequest
from app.schemas.wizard import Tags as _Tags
from loguru import logger

router = APIRouter()

# 响应模型映射表（内置）
from app.schemas.response_registry import RESPONSE_MODEL_MAP


@router.get("/schemas", response_model=Dict[str, Any], summary="获取所有输出模型的JSON Schema（仅内置）")
def get_all_schemas(session: Session = Depends(get_session)):
    """返回内置 pydantic 模型的 schema 聚合，键为模型名称。"""
    all_definitions: Dict[str, Any] = {}

    # 1) 内置 pydantic 模型
    for name, model_class in RESPONSE_MODEL_MAP.items():
        schema = model_class.model_json_schema(ref_template="#/$defs/{model}")
        if '$defs' in schema:
            all_definitions.update(schema['$defs'])
            del schema['$defs']
        all_definitions[name] = schema

    # 动态修复 CharacterCard.dynamic_info 的属性
    try:
        cc = all_definitions.get('CharacterCard')
        if isinstance(cc, dict):
            props = (cc.get('properties') or {})
            if 'dynamic_info' in props:
                item_schema = {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "info": {"type": "string"},
                        "weight": {"type": "number"}
                    },
                    "required": ["id", "info", "weight"]
                }
                enum_values = DYNAMIC_INFO_TYPES
                props['dynamic_info'] = {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        ev: {"type": "array", "items": item_schema} for ev in enum_values
                    },
                    "description": "角色动态信息，按类别分组的数组（键为中文枚举值）"
                }
                cc['properties'] = props
                all_definitions['CharacterCard'] = cc
    except Exception:
        pass

    # 2) 注入 entity 动态信息相关模型（用于前端解析 $ref: DynamicInfo 等）
    try:
        entity_models = [
            entity_schemas.DynamicInfoItem,
            entity_schemas.DynamicInfo,
            entity_schemas.UpdateDynamicInfo,
        ]
        for mdl in entity_models:
            sch = mdl.model_json_schema(ref_template="#/$defs/{model}")
            if '$defs' in sch:
                all_definitions.update(sch['$defs'])
                del sch['$defs']
            all_definitions[mdl.__name__] = sch
    except Exception:
        pass

    return all_definitions

@router.get("/content-models", response_model=List[str], summary="获取所有可用输出模型名称")
def get_content_models(session: Session = Depends(get_session)):
    # 仅返回内置模型名称
    return list(RESPONSE_MODEL_MAP.keys())


@router.get("/config-options", summary="获取AI生成配置选项")
async def get_ai_config_options(session: Session = Depends(get_session)):
    """获取AI生成时可用的配置选项"""
    try:
        # 获取所有LLM配置
        llm_configs = llm_config_service.get_llm_configs(session)
        # 获取所有提示词
        prompts = prompt_service.get_prompts(session)
        # 响应模型仅内置
        response_models = get_content_models(session)
        return ApiResponse(data={
            "llm_configs": [{"id": config.id, "display_name": config.display_name or config.model_name} for config in llm_configs],
            "prompts": [{"id": prompt.id, "name": prompt.name, "description": prompt.description, "built_in": getattr(prompt, 'built_in', False)} for prompt in prompts],
            "available_tasks": [],
            "response_models": response_models
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置选项失败: {str(e)}")

@router.get("/prompts/render", summary="渲染并注入知识库的提示词模板")
async def render_prompt_with_knowledge(name: str, session: Session = Depends(get_session)):
    p = prompt_service.get_prompt_by_name(session, name)
    if not p or not p.template:
        raise HTTPException(status_code=404, detail=f"未找到提示词: {name}")
    try:
        text = prompt_service.inject_knowledge(session, str(p.template))
        return ApiResponse(data={"text": text})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"渲染失败: {e}")

@router.post("/generate", summary="通用AI生成接口")
async def generate_ai_content(
    request: GeneralAIRequest = Body(...),
    session: Session = Depends(get_session),
):
    """
    通用的AI内容生成端点：前端必须提供 response_model_schema。
    """
    # 基本参数校验：input/llm_config_id/prompt_name/response_model_schema 必填
    if not request.input or not request.llm_config_id or not request.prompt_name:
        raise HTTPException(status_code=400, detail="缺少必要的生成参数: input, llm_config_id 或 prompt_name")
    if request.response_model_schema is None:
        raise HTTPException(status_code=400, detail="请提供 response_model_schema")

    # 解析响应模型（仅动态 schema）
    try:
        # 完整 Schema 组装：内置 defs + CardType defs
        composed = compose_full_schema(session, request.response_model_schema)
        # 基于 x-ai-exclude 过滤字段
        schema_for_prompt = filter_schema_for_ai(composed) if request.exclude_ai_fields else composed
        # 动态构建 Pydantic 模型
        resp_model = build_model_from_json_schema('DynamicResponseModel', schema_for_prompt or composed)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"动态创建模型失败: {e}")

    # 获取提示词
    prompt = prompt_service.get_prompt_by_name(session, request.prompt_name)
    if not prompt:
        raise HTTPException(status_code=400, detail=f"未找到提示词名称: {request.prompt_name}")

    # 注入知识库
    prompt_template = prompt_service.inject_knowledge(session, prompt.template or '')

    # System Prompt：携带 JSON Schema
    schema_json = json.dumps(schema_for_prompt if schema_for_prompt is not None else resp_model.model_json_schema(), indent=2, ensure_ascii=False)
    system_prompt = (
        f"{prompt_template}\n\n"
        f"```json\n{schema_json}\n```"
    )

    user_prompt = request.input['input_text']
    deps_str = request.deps or ""

    try:
        result = await llm_service.generate_structured(
            session=session,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            output_type=resp_model,
            llm_config_id=request.llm_config_id, 
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            timeout=request.timeout,
            deps=deps_str,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 触发 OnGenerateFinish（若能定位 card）
    card: Card | None = None
    try:
        card_id = None
        if isinstance(request.input, dict):
            card_id = request.input.get('card_id')
        if card_id:
            card = session.get(Card, int(card_id))
        project_id = None
        if isinstance(request.input, dict):
            project_id = request.input.get('project_id') or (card.project_id if card else None)
        emit_event("generate.finished", {
            "session": session,
            "card": card,
            "project_id": int(project_id) if project_id else (card.project_id if card else None)
        })
    except Exception:
        pass
    return ApiResponse(data=result)

@router.post("/generate/continuation", 
             response_model=ApiResponse[ContinuationResponse], 
             summary="续写正文",
             responses={
                 200: {
                     "content": {
                         "application/json": {},
                         "text/event-stream": {}
                     },
                     "description": "成功返回续写结果或事件流"
                 }
             })
async def generate_continuation(
    request: ContinuationRequest,
    session: Session = Depends(get_session),
):
    try:
        # 强制从 prompt_name 读取模板作为 system prompt
        if not request.prompt_name:
            raise HTTPException(status_code=400, detail="续写必须指定 prompt_name")
        p = prompt_service.get_prompt_by_name(session, request.prompt_name)
        if not p or not p.template:
            raise HTTPException(status_code=400, detail=f"未找到提示词名称: {request.prompt_name}")
        # 注入知识库
        system_prompt = prompt_service.inject_knowledge(session, str(p.template))

        if request.stream:
            # 先做一次配额预检，避免流式过程中才抛错
            ok, reason = _llm_svc.can_consume(session, request.llm_config_id, 0, 0, 1)
            if not ok:
                raise HTTPException(status_code=400, detail=f"LLM 配额不足：{reason}")
            async def _stream_and_trigger():
                content_acc = []
                async for chunk in llm_service.generate_continuation_streaming(session, request, system_prompt):
                    content_acc.append(chunk)
                    yield chunk
                try:
                    # 续写结束后触发
                    emit_event("generate.finished", {
                        "session": session,
                        "card": None,
                        "project_id": request.project_id
                    })
                except Exception:
                    pass
            return StreamingResponse(wrap_sse_stream(_stream_and_trigger()), media_type="text/event-stream")
        else:
            # 非流式模式：收集所有内容
            content_parts = []
            async for chunk in llm_service.generate_continuation_streaming(session, request, system_prompt):
                content_parts.append(chunk)
            result = "".join(content_parts)
            try:
                emit_event("generate.finished", {
                    "session": session,
                    "card": None,
                    "project_id": request.project_id
                })
            except Exception:
                pass
            return ApiResponse(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@router.get("/models/tags", response_model=_Tags, summary="导出 Tags 模型（用于类型生成）")
def export_tags_model():
    return _Tags()


# ==================== 指令流生成端点 ====================


@router.post("/generate/stream", summary="指令流式生成端点")
async def generate_with_instruction_stream(
    request: InstructionGenerateRequest,
    session: Session = Depends(get_session),
):
    """
    指令流式生成端点
    
    实时返回 LLM 生成的指令流，前端逐条执行并更新 UI。
    支持自动校验和修复，用户可以在生成过程中与 AI 交互。
    """
    async def event_generator():
        try:
            # 1. 组装完整 Schema（注入 $defs）
            full_schema = compose_full_schema(session, request.response_model_schema)
            
            # 2. 加载卡片任务提示词（如果提供了名称）
            card_prompt_content = None
            if request.prompt_template:
                from app.services import prompt_service
                from loguru import logger
                prompt = prompt_service.get_prompt_by_name(session, request.prompt_template)
                if prompt and prompt.template:
                    card_prompt_content = prompt.template
                    logger.info(f"[卡片生成] 加载提示词模板: {request.prompt_template}, 长度: {len(card_prompt_content)}")
                else:
                    logger.warning(f"[卡片生成] 未找到提示词模板: {request.prompt_template}")
            
            # 3. 构建 System Prompt（卡片任务 + 指令规范 + Schema）
            system_prompt = build_instruction_system_prompt(
                session=session,
                schema=full_schema,
                card_prompt=card_prompt_content
            )
            
            # 4. 调用指令流生成服务
            async for event in generate_instruction_stream(
                session=session,
                llm_config_id=request.llm_config_id,
                user_prompt=request.user_prompt,
                system_prompt=system_prompt,
                schema=full_schema,
                current_data=request.current_data,
                conversation_context=request.conversation_context,
                context_info=request.context_info,
                temperature=request.temperature or 0.7,
                max_tokens=request.max_tokens,
                timeout=request.timeout or 150
            ):
                # 5. 发送 SSE 事件（格式：data: {json}\n\n）
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        
        except Exception as e:
            logger.error(f"指令流生成失败: {e}", exc_info=True)
            error_event = {
                "type": "error",
                "text": f"生成失败: {str(e)}"
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    ) 