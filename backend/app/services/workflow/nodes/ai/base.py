"""AI 节点基类

提供 AI 相关节点的通用配置和工具。
"""

from pydantic import Field
from ..base import BaseNodeConfig


class BaseAINodeConfig(BaseNodeConfig):
    """AI 节点基础配置"""
    
    llm_config_id: int = Field(
        ...,
        description="LLM 配置 ID",
        json_schema_extra={"x-component": "LLMSelect"}
    )
    temperature: float = Field(
        0.7,
        ge=0.0,
        le=2.0,
        description="温度参数"
    )
    max_tokens: int = Field(
        4096,
        ge=1,
        description="最大 token 数"
    )
