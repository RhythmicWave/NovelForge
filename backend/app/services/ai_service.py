from typing import Optional, Dict, Any, AsyncGenerator
from pydantic import BaseModel, Field
from sqlmodel import Session
from app.schemas.response_registry import RESPONSE_MODEL_MAP
from app.services import agent_service, prompt_service
import json
from loguru import logger

class ContinuationResponse(BaseModel):
    """AI续写的响应模型"""
    continuation: str = Field(description="AI生成的续写内容")

class ContinuationRequest(BaseModel):
    """请求AI续写的模型"""
    llm_config_id: int
    prompt_id: int
    context: Dict[str, Any]  # 用于填充提示词模板的上下文
    max_tokens: Optional[int] = 5000
    temperature: Optional[float] = 0.7
    stream: bool = False

def extract_text_content(tiptap_content: Dict[Any, Any]) -> str:
    """从Tiptap编辑器的JSON内容中提取纯文本"""
    if not tiptap_content:
        return ""
    
    try:
        # 尝试从content字段中获取文本
        if "content" in tiptap_content:
            text_parts = []
            for item in tiptap_content["content"]:
                if item.get("type") == "paragraph" and "content" in item:
                    for content_item in item["content"]:
                        if content_item.get("type") == "text":
                            text_parts.append(content_item.get("text", ""))
            return " ".join(text_parts)
        else:
            # 如果找不到结构化内容，尝试将整个内容转换为字符串
            return json.dumps(tiptap_content, ensure_ascii=False)
    except Exception as e:
        logger.error(f"提取文本内容时出错: {e}")
        return json.dumps(tiptap_content, ensure_ascii=False)

async def generate_continuation(session: Session, request: ContinuationRequest) -> ContinuationResponse:
    """生成AI续写内容"""
    # 1. 获取提示词模板
    db_prompt = prompt_service.get_prompt(session, request.prompt_id)
    if not db_prompt:
        raise ValueError(f"提示词未找到，ID: {request.prompt_id}")

    # 2. 渲染提示词
    final_prompt = prompt_service.render_prompt(db_prompt.template, request.context)
    
    # 3. 调用封装好的LLM Agent服务
    try:
        result = await agent_service.run_llm_agent(
            session=session,
            llm_config_id=request.llm_config_id,
            user_prompt=final_prompt,
            output_type=ContinuationResponse,
            system_prompt="你是一位专业的小说创作助手，擅长根据已有内容续写故事。",
            max_tokens=request.max_tokens,
            temperature=request.temperature
        )
        return result
    except ValueError as e:
        logger.error(f"生成续写内容时出错: {e}")
        raise e

async def generate_continuation_streaming(
    session: Session, request: ContinuationRequest
) -> AsyncGenerator[str, None]:
    """以流式方式生成AI续写内容"""
    # 1. 获取提示词模板
    db_prompt = prompt_service.get_prompt(session, request.prompt_id)
    if not db_prompt:
        raise ValueError(f"提示词未找到，ID: {request.prompt_id}")

    # 2. 渲染提示词
    final_prompt = prompt_service.render_prompt(db_prompt.template, request.context)

    try:
        async for text_chunk in agent_service.run_llm_agent_streaming(
            session=session,
            llm_config_id=request.llm_config_id,
            prompt=final_prompt,
            system_prompt="你是一位专业的小说创作助手，擅长根据已有内容续写故事。",
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        ):
            yield text_chunk
    except ValueError as e:
        logger.error(f"生成流式续写内容时出错: {e}")
        raise e 