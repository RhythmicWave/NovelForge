from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.llm_config import (
    LLMConfigCreate,
    LLMConfigRead,
    LLMConfigUpdate,
    LLMConnectionTest,
    LLMGetModelsRequest,
)
from app.schemas.response import ApiResponse
from app.services import llm_config_service
from app.services.ai.core.chat_model_factory import build_chat_model_from_payload


router = APIRouter()


@router.post("/", response_model=ApiResponse[LLMConfigRead])
def create_llm_config_endpoint(config_in: LLMConfigCreate, session: Session = Depends(get_session)):
    if config_in.display_name is None or config_in.display_name == "":
        config_in.display_name = config_in.model_name
    config = llm_config_service.create_llm_config(session=session, config_in=config_in)
    return ApiResponse(data=config)


@router.get("/", response_model=ApiResponse[List[LLMConfigRead]])
def get_llm_configs_endpoint(session: Session = Depends(get_session)):
    configs = llm_config_service.get_llm_configs(session=session)
    return ApiResponse(data=configs)


@router.put("/{config_id}", response_model=ApiResponse[LLMConfigRead])
def update_llm_config_endpoint(config_id: int, config_in: LLMConfigUpdate, session: Session = Depends(get_session)):
    config = llm_config_service.update_llm_config(session=session, config_id=config_id, config_in=config_in)
    if not config:
        raise HTTPException(status_code=404, detail="LLM Config not found")
    return ApiResponse(data=config)


@router.delete("/{config_id}", response_model=ApiResponse)
def delete_llm_config_endpoint(config_id: int, session: Session = Depends(get_session)):
    success = llm_config_service.delete_llm_config(session=session, config_id=config_id)
    if not success:
        raise HTTPException(status_code=404, detail="LLM Config not found")
    return ApiResponse(message="LLM Config deleted successfully")


@router.post("/get-models", response_model=ApiResponse[List[str]], summary="获取模型列表")
async def get_models_endpoint(request: LLMGetModelsRequest):
    provider = (request.provider or "").lower()
    models: list[str] = []

    try:
        if provider in {"openai_compatible", "openai"}:
            transport = llm_config_service.resolve_transport_settings(
                provider=provider,
                api_base=request.api_base,
                api_protocol=request.api_protocol,
                models_path=request.models_path,
                user_agent=request.user_agent,
            )
            if not transport["models_url"]:
                raise ValueError("缺少 api_base，无法获取模型列表")

            headers = {
                "Authorization": f"Bearer {request.api_key}",
                "Content-Type": "application/json",
                **transport["default_headers"],
            }
            async with httpx.AsyncClient() as client:
                response = await client.get(transport["models_url"], headers=headers, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                if "data" in data and isinstance(data["data"], list):
                    models = [item["id"] for item in data["data"] if "id" in item]

        elif provider == "google":
            if request.api_key:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"https://generativelanguage.googleapis.com/v1beta/models?key={request.api_key}",
                        timeout=10.0,
                    )
                    response.raise_for_status()
                    data = response.json()
                    if "models" in data and isinstance(data["models"], list):
                        models = [m["name"].replace("models/", "") for m in data["models"] if "name" in m]

        return ApiResponse(data=models)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"获取模型列表失败: {str(e)}")


@router.post("/test", response_model=ApiResponse, summary="测试 LLM 连接")
async def test_llm_connection_endpoint(connection_data: LLMConnectionTest):
    """使用临时传输配置构建 ChatModel 并执行最小调用。"""
    try:
        model = build_chat_model_from_payload(
            provider=connection_data.provider,
            model_name=connection_data.model_name,
            api_key=connection_data.api_key,
            api_base=connection_data.api_base,
            api_protocol=connection_data.api_protocol,
            custom_request_path=connection_data.custom_request_path,
            user_agent=connection_data.user_agent,
        )
        await model.ainvoke("ping")
        return ApiResponse(message="Connection successful")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"连接测试失败: {e}")


@router.post("/{config_id}/reset-usage", response_model=ApiResponse, summary="重置统计（输入/输出 token 与调用次数）")
def reset_llm_usage(config_id: int, session: Session = Depends(get_session)):
    ok = llm_config_service.reset_usage(session, config_id)
    if not ok:
        raise HTTPException(status_code=404, detail="LLM Config not found")
    return ApiResponse(message="Usage reset")


@router.post("/{config_id}/copy", response_model=ApiResponse[LLMConfigRead], summary="复制 LLM 配置")
def copy_llm_config_endpoint(config_id: int, session: Session = Depends(get_session)):
    config = llm_config_service.copy_llm_config(session=session, config_id=config_id)
    if not config:
        raise HTTPException(status_code=404, detail="LLM Config not found")
    return ApiResponse(data=config, message="LLM Config copied successfully")
