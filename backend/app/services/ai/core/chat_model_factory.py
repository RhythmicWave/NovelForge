"""ChatModel 工厂。

集中管理 LLM 配置读取与 LangChain ChatModel 构建，避免业务层模块相互依赖。
"""

from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_qwq import ChatQwen
from sqlmodel import Session

from app.db.models import LLMConfig
from app.services import llm_config_service


def _get_llm_config(session: Session, llm_config_id: int) -> LLMConfig:
    """获取 LLM 配置。"""
    cfg = llm_config_service.get_llm_config(session, llm_config_id)
    if not cfg:
        raise ValueError(f"LLM配置不存在，ID: {llm_config_id}")
    if not cfg.api_key:
        raise ValueError(f"未找到LLM配置 {cfg.display_name or cfg.model_name} 的API密钥")
    return cfg


def build_chat_model(
    session: Session,
    llm_config_id: int,
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
    thinking_enabled: Optional[bool] = None,
):
    """构建 LangChain ChatModel 实例。"""
    cfg = _get_llm_config(session, llm_config_id)
    provider = (cfg.provider or "").lower()

    common_kwargs: dict = {}
    if temperature is not None:
        common_kwargs["temperature"] = float(temperature)
    if max_tokens is not None:
        common_kwargs["max_tokens"] = int(max_tokens)
    if timeout is not None:
        common_kwargs["timeout"] = float(timeout)

    if provider == "openai_compatible":
        model_kwargs: dict = {
            "model": cfg.model_name,
            "api_key": cfg.api_key,
        }
        if cfg.api_base:
            model_kwargs["base_url"] = cfg.api_base
        if thinking_enabled is not None:
            model_kwargs["extra_body"] = {"enable_thinking": thinking_enabled}
        model_kwargs.update(common_kwargs)
        return ChatQwen(**model_kwargs)

    if provider == "openai":
        model_kwargs = {
            "model": cfg.model_name,
            "api_key": cfg.api_key,
        }
        model_kwargs.update(common_kwargs)
        return ChatOpenAI(**model_kwargs)

    if provider == "anthropic":
        model_kwargs = {
            "model": cfg.model_name,
            "api_key": cfg.api_key,
        }
        if thinking_enabled is True:
            model_kwargs["thinking"] = {"type": "enabled", "budget_tokens": 2048}
        model_kwargs.update(common_kwargs)
        return ChatAnthropic(**model_kwargs)

    if provider == "google":
        model_kwargs = {
            "model": cfg.model_name,
            "api_key": cfg.api_key,
        }
        if thinking_enabled is not None:
            model_kwargs["include_thoughts"] = thinking_enabled
        if max_tokens is not None:
            model_kwargs["max_output_tokens"] = int(max_tokens)
            model_kwargs.pop("max_tokens", None)
        if temperature is not None:
            model_kwargs["temperature"] = float(temperature)
        return ChatGoogleGenerativeAI(**model_kwargs)

    raise ValueError(f"不支持的LLM提供商: {cfg.provider}")

