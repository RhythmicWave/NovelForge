"""结构化生成节点

利用指令流生成服务（Instruction Generator）实现结构化数据的生成。
支持自动校验、自动修复和 Pydantic 模型输出。
"""

from typing import Any, Dict, Optional, List
from pydantic import Field
from loguru import logger
import json

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode
from .base import BaseAINodeConfig
from app.services.ai.generation.instruction_generator import generate_instruction_stream
from app.services.schema_service import compose_full_schema
from app.db.models import CardType
from app.schemas.response_registry import RESPONSE_MODEL_MAP
from sqlmodel import select

class StructuredGenerateConfig(BaseAINodeConfig):
    """结构化生成配置"""
    response_model_id: str = Field(..., description="模型标识 (内置模型名或CardType名称)", json_schema_extra={"x-component": "ResponseModelSelect"})
    max_retry: int = Field(3, description="最大重试/修复次数")
    prompt_template: Optional[str] = Field(None, description="提示词模版名称(可选)", json_schema_extra={"x-component": "PromptSelect"})

@register_node
class StructuredGenerateNode(BaseNode):
    """结构化生成节点"""
    
    node_type = "AI.StructuredGenerate"
    category = "ai"
    label = "结构化生成"
    description = "生成符合指定 Schema 的结构化数据 (支持自动修复)"
    config_model = StructuredGenerateConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("user_prompt", "string", description="用户提示词"),
                NodePort("context", "object", required=False, description="上下文数据/初始数据"),
                NodePort("schema_extra", "object", required=False, description="额外的 Schema 定义 (可选)")
            ],
            "outputs": [
                NodePort("data", "object", description="生成的结构化数据"),
                NodePort("logs", "array", description="生成过程日志"),
            ]
        }

    async def execute(
        self,
        inputs: Dict[str, Any],
        config: StructuredGenerateConfig
    ) -> ExecutionResult:
        """执行生成"""
        session = self.context.session
        user_prompt = inputs.get("user_prompt", "")
        current_data = inputs.get("context", {}) or {}
        
        # 1. 获取目标 Schema
        target_schema = self._get_schema(session, config)
        if not target_schema:
            return ExecutionResult(success=False, error=f"无法加载模型 Schema: {config.response_model_id}")
            
        # 2. 准备参数
        # 组装完整 Schema (处理 $ref)
        full_schema = compose_full_schema(session, target_schema)
        
        # 构建 System Prompt (复用 instruction_generator 内部逻辑，通过传入 schema 让其自动构建)
        # generate_instruction_stream 会自动处理 system prompt 的构建，只要我们传入 schema
        from app.services.ai.generation.prompt_builder import build_instruction_system_prompt
        
        # 加载提示词模板（如果配置了）
        card_prompt_content = None
        if config.prompt_template:
            from app.services import prompt_service
            prompt = prompt_service.get_prompt_by_name(session, config.prompt_template)
            if prompt and prompt.template:
                card_prompt_content = prompt.template

        system_prompt = build_instruction_system_prompt(
            session=session,
            schema=full_schema,
            card_prompt=card_prompt_content
        )
        
        logger.info(f"[AI.Structured] 开始生成: model={config.response_model_id}, type={config.response_model_type}")
        
        # 3. 调用生成流 (非流式消费)
        final_data = None
        logs = []
        conversation_context = [] # 暂时为空，未来可以支持传入对话历史
        
        try:
            # 消费 generator
            async for event in generate_instruction_stream(
                session=session,
                llm_config_id=config.llm_config_id,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                schema=full_schema,
                current_data=current_data,
                conversation_context=conversation_context,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                timeout=config.timeout,
                max_retry=config.max_retry
            ):
                event_type = event.get("type")
                
                # 记录重要日志
                if event_type in ["thinking", "warning", "error", "done"]:
                    logs.append(event)
                
                if event_type == "instruction":
                    # 指令已在 generator 内部应用到 collected_data，
                    # 但 generator 在 done 事件中才会返回最终校验过的数据
                    pass
                    
                if event_type == "done":
                    if event.get("success"):
                        final_data = event.get("final_data")
                    else:
                        logger.warning(f"[AI.Structured] 生成结束但未标记成功: {event.get('message')}")
                        
                if event_type == "error":
                    logger.error(f"[AI.Structured] 生成过程错误: {event.get('text')}")
        
        except Exception as e:
            logger.exception(f"[AI.Structured] 执行异常")
            return ExecutionResult(success=False, error=str(e))
            
        if final_data is None:
             return ExecutionResult(success=False, error="生成未能完成，未获取到有效数据")
             
        return ExecutionResult(
            success=True,
            outputs={
                "data": final_data,
                "logs": logs
            }
        )

    def _get_schema(self, session, config: StructuredGenerateConfig) -> Optional[Dict[str, Any]]:
        """根据配置获取 JSON Schema
        
        自动判断是内置模型还是自定义CardType:
        1. 先尝试从内置模型中查找
        2. 如果找不到,再从CardType中查找
        """
        # 1. 尝试内置模型
        model_cls = RESPONSE_MODEL_MAP.get(config.response_model_id)
        if model_cls:
            return model_cls.model_json_schema()
        
        # 2. 尝试自定义 CardType
        stmt = select(CardType).where(CardType.name == config.response_model_id)
        ct = session.exec(stmt).first()
        if ct and ct.json_schema:
            return ct.json_schema
                
        return None
