
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from app.db.session import get_session
from app.schemas.llm_config import LLMConfigCreate, LLMConfigRead, LLMConfigUpdate, LLMConnectionTest
from app.schemas.response import ApiResponse
from app.services import llm_config_service
from typing import List
from app.services.agent_service import _get_agent
from pydantic import BaseModel

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

@router.post("/test", response_model=ApiResponse, summary="测试 LLM 连接")
async def test_llm_connection_endpoint(connection_data: LLMConnectionTest, session: Session = Depends(get_session)):
    """使用传入参数临时构造一个 Agent 并发起一次最小调用以验证连通性。"""
    try:
        # 临时保存配置到内存对象，不落库：走 provider/openai 风格
        # 复用 _get_agent 能力，传入一个极简输出类型
        class _PingModel(BaseModel):
            ok: bool = True

        # 临时将参数注入到 session 的 get_llm_config 逻辑不可行，这里直接构造 provider
        # 简单走 openai 兼容路径：在 Agent 层会使用 provider/base_url
        # 因 _get_agent 依赖后端存储的 LLMConfig，此处提供一个简易直连测试：
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai import Agent
        from pydantic_ai.settings import ModelSettings

        provider_cfg = {"api_key": connection_data.api_key}
        if connection_data.api_base:
            provider_cfg["base_url"] = connection_data.api_base
        provider = OpenAIProvider(**provider_cfg)
        model = OpenAIModel(connection_data.model_name, provider=provider)
        agent = Agent(model, system_prompt="你是一个助手。", model_settings=ModelSettings(timeout=15))
        # 发送最小请求
        await agent.run("ping")
        return ApiResponse(message="Connection successful")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"连接测试失败: {e}")


@router.post("/{config_id}/reset-usage", response_model=ApiResponse, summary="重置统计（输入/输出token与调用次数清零）")
def reset_llm_usage(config_id: int, session: Session = Depends(get_session)):
    ok = llm_config_service.reset_usage(session, config_id)
    if not ok:
        raise HTTPException(status_code=404, detail="LLM Config not found")
    return ApiResponse(message="Usage reset")