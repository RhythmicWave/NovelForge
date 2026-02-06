"""LLM 生成节点

提供单轮 LLM 调用能力，支持提示词模板和结构化输出。
"""

from typing import Any, Dict, Optional
from pydantic import Field
from loguru import logger

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode
from .base import BaseAINodeConfig
from app.services.ai.core.llm_service import build_chat_model
from app.services.prompt_service import get_prompt, render_prompt
from langchain_core.messages import HumanMessage, SystemMessage


class LLMGenerateConfig(BaseAINodeConfig):
    """LLM 生成配置"""
    max_retry: int = Field(3, description="最大重试次数", ge=0, le=10)


@register_node
class LLMGenerateNode(BaseNode):
    """LLM 生成节点"""
    
    node_type = "AI.LLM"
    category = "ai"
    label = "LLM 调用"
    description = "调用大语言模型进行文本生成"
    config_model = LLMGenerateConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("system_prompt", "string", required=False, description="系统提示词"),
                NodePort("user_prompt", "string", description="用户提示词"),
            ],
            "outputs": [
                NodePort("response", "string", description="生成的文本"),
                NodePort("usage", "object", description="Token 使用统计"),
            ]
        }

    async def execute(
        self,
        inputs: Dict[str, Any],
        config: LLMGenerateConfig
    ) -> ExecutionResult:
        """执行 LLM 调用"""
        
        user_prompt = inputs.get("user_prompt", "")
        system_prompt = inputs.get("system_prompt", "")
        
        # 构建 ChatModel (在重试循环外,避免重复构建)
        try:
            model = build_chat_model(
                session=self.context.session,
                llm_config_id=config.llm_config_id,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                timeout=config.timeout,
            )
        except Exception as e:
            logger.error(f"[AI.LLM] 构建模型失败: {e}")
            return ExecutionResult(
                success=False,
                error=f"构建模型失败: {str(e)}"
            )
        
        # 构建消息
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=user_prompt))
        
        # 重试循环
        last_error = None
        for attempt in range(config.max_retry + 1):  # +1 因为第一次不算重试
            try:
                # 调用模型
                response = await model.ainvoke(messages)
                
                # 提取文本
                response_text = response.content if hasattr(response, 'content') else str(response)
                
                # 提取 usage 信息
                usage = {}
                if hasattr(response, 'usage_metadata'):
                    usage = response.usage_metadata
                elif hasattr(response, 'response_metadata'):
                    meta = response.response_metadata
                    if isinstance(meta, dict):
                        usage = meta.get('usage', {})
                
                logger.info(
                    f"[AI.LLM] LLM 调用成功 (尝试 {attempt + 1}/{config.max_retry + 1}): "
                    f"llm_config_id={config.llm_config_id}, response_length={len(response_text)}"
                )
                
                return ExecutionResult(
                    success=True,
                    outputs={
                        "response": response_text,
                        "usage": usage,
                    }
                )
                
            except Exception as e:
                last_error = e
                if attempt < config.max_retry:
                    logger.warning(
                        f"[AI.LLM] LLM 调用失败 (尝试 {attempt + 1}/{config.max_retry + 1}), "
                        f"将重试: {str(e)}"
                    )
                else:
                    logger.error(
                        f"[AI.LLM] LLM 调用失败,已达最大重试次数 ({config.max_retry + 1}): {str(e)}"
                    )
        
        # 所有重试都失败
        return ExecutionResult(
            success=False,
            error=f"LLM 调用失败 (重试{config.max_retry}次后): {str(last_error)}"
        )
