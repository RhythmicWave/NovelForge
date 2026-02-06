"""结构化生成节点

利用指令流生成服务（Instruction Generator）实现结构化数据的生成。
支持自动校验、自动修复和 Pydantic 模型输出。
"""

from typing import Any, Dict, Optional, List, AsyncIterator, Union, TYPE_CHECKING
from pydantic import BaseModel, Field
from loguru import logger
import json

if TYPE_CHECKING:
    from ...engine.async_executor import ProgressEvent

from ...registry import register_node
from ..base import BaseNode
from app.services.ai.generation.instruction_generator import generate_instruction_stream
from app.services.schema_service import compose_full_schema
from app.db.models import CardType
from app.schemas.response_registry import RESPONSE_MODEL_MAP
from sqlmodel import select


class StructuredGenerateInput(BaseModel):
    """结构化生成输入"""
    user_prompt: str = Field(..., description="用户提示词")
    llm_config_id: int = Field(..., description="LLM配置ID", json_schema_extra={"x-component": "LLMSelect"})
    response_model_id: str = Field(..., description="模型标识 ", json_schema_extra={"x-component": "ResponseModelSelect"})
    context: Optional[Dict[str, Any]] = Field(None, description="上下文数据/初始数据")
    schema_extra: Optional[Dict[str, Any]] = Field(None, description="额外的 Schema 定义 (可选)")
    max_retry: int = Field(3, description="最大重试/修复次数")
    prompt_template: Optional[str] = Field(None, description="提示词模版名称(可选)", json_schema_extra={"x-component": "PromptSelect"})
    temperature: float = Field(0.7, description="温度参数")
    max_tokens: Optional[int] = Field(None, description="最大token数")
    timeout: int = Field(60, description="超时时间(秒)")


class StructuredGenerateOutput(BaseModel):
    """结构化生成输出"""
    data: Dict[str, Any] = Field(..., description="生成的结构化数据")
    logs: List[Dict[str, Any]] = Field(..., description="生成过程日志")

@register_node
class StructuredGenerateNode(BaseNode[StructuredGenerateInput, StructuredGenerateOutput]):
    """结构化生成节点"""
    
    node_type = "AI.StructuredGenerate"
    category = "ai"
    label = "结构化生成"
    description = "生成符合指定 Schema 的结构化数据 (支持自动修复)"
    
    input_model = StructuredGenerateInput
    output_model = StructuredGenerateOutput

    async def execute(
        self,
        inputs: StructuredGenerateInput
    ) -> AsyncIterator[StructuredGenerateOutput]:
        """执行生成"""
        session = self.context.session
        user_prompt = inputs.user_prompt
        current_data = inputs.context or {}
        
        # 1. 获取目标 Schema
        target_schema = self._get_schema(session, inputs)
        if not target_schema:
            raise ValueError(f"无法加载模型 Schema: {inputs.response_model_id}")
            
        # 2. 准备参数
        # 组装完整 Schema (处理 $ref)
        full_schema = compose_full_schema(session, target_schema)
        
        # 构建 System Prompt
        from app.services.ai.generation.prompt_builder import build_instruction_system_prompt
        
        # 加载提示词模板（如果配置了）
        card_prompt_content = None
        if inputs.prompt_template:
            from app.services import prompt_service
            prompt = prompt_service.get_prompt_by_name(session, inputs.prompt_template)
            if prompt and prompt.template:
                card_prompt_content = prompt.template

        system_prompt = build_instruction_system_prompt(
            session=session,
            schema=full_schema,
            card_prompt=card_prompt_content
        )
        
        logger.info(f"[AI.Structured] 开始生成: model={inputs.response_model_id}")
        
        # 3. 调用生成流 (非流式消费)
        final_data = None
        logs = []
        conversation_context = []  # 暂时为空，未来可以支持传入对话历史
        
        try:
            # 消费 generator
            async for event in generate_instruction_stream(
                session=session,
                llm_config_id=inputs.llm_config_id,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                schema=full_schema,
                current_data=current_data,
                conversation_context=conversation_context,
                temperature=inputs.temperature,
                max_tokens=inputs.max_tokens,
                timeout=inputs.timeout,
                max_retry=inputs.max_retry
            ):
                event_type = event.get("type")
                
                # 记录重要日志
                if event_type in ["thinking", "warning", "error", "done"]:
                    logs.append(event)
                
                if event_type == "instruction":
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
            raise
            
        if final_data is None:
            raise ValueError("生成未能完成，未获取到有效数据")
             
        yield StructuredGenerateOutput(
            data=final_data,
            logs=logs
        )

    def _get_schema(self, session, inputs: StructuredGenerateInput) -> Optional[Dict[str, Any]]:
        """根据配置获取 JSON Schema
        """
        
        stmt = select(CardType).where(CardType.name == inputs.response_model_id)
        ct = session.exec(stmt).first()
        if ct and ct.json_schema:
            return ct.json_schema
                
        return None
