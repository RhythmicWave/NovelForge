from typing import Awaitable, Callable, Optional, Type, Any, Dict, AsyncGenerator, Union
from fastapi import Response
from json_repair import repair_json
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from sqlmodel import Session
from app.services import llm_config_service
from loguru import logger
from app.schemas.ai import ContinuationRequest
from app.services import prompt_service

def _get_agent(session: Session, llm_config_id: int, output_type: Type[BaseModel], system_prompt: str='') -> Agent:
    """
    根据LLM配置和期望的输出类型，获取一个配置好的LLM Agent实例。
    这是一个内部函数，用于封装Agent的初始化逻辑。
    """
    llm_config = llm_config_service.get_llm_config(session, llm_config_id)
    if not llm_config:
        raise ValueError(f"LLM配置不存在，ID: {llm_config_id}")
    
    logger.debug(f"LLM配置: provider={llm_config.provider}, model_name={llm_config.model_name}, api_key存在={bool(llm_config.api_key)}")
    
    if not llm_config.api_key:
        raise ValueError(f"未找到LLM配置 {llm_config.display_name or llm_config.model_name} 的API密钥")
    
    # 根据提供商类型创建相应的Provider和Model
    if llm_config.provider == "openai":
        # 创建OpenAI Provider
        provider_config = {
            "api_key": llm_config.api_key
        }
        
        if llm_config.api_base:
            provider_config["base_url"] = llm_config.api_base
        
        logger.debug(f"OpenAI Provider配置: {provider_config}")
        
        # 创建OpenAI Provider和Model
        provider = OpenAIProvider(**provider_config)
        model = OpenAIModel(llm_config.model_name, provider=provider)
        
    elif llm_config.provider == "anthropic":
        # 创建Anthropic Provider
        provider_config = {
            "api_key": llm_config.api_key
        }
        
        if llm_config.api_base:
            provider_config["base_url"] = llm_config.api_base
        
        logger.debug(f"Anthropic Provider配置: {provider_config}")
        
        # 创建Anthropic Provider和Model
        provider = AnthropicProvider(**provider_config)
        model = AnthropicModel(llm_config.model_name, provider=provider)
        
    elif llm_config.provider == "custom":
        # 自定义提供商，默认使用OpenAI格式
        provider_config = {
            "api_key": llm_config.api_key
        }
        
        if llm_config.api_base:
            provider_config["base_url"] = llm_config.api_base
        
        logger.debug(f"Custom Provider配置: {provider_config}")
        
        # 使用OpenAI格式作为自定义提供商
        provider = OpenAIProvider(**provider_config)
        model = OpenAIModel(llm_config.model_name, provider=provider)
        
    else:
        raise ValueError(f"不支持的提供商类型: {llm_config.provider}")

    agent=Agent(model,system_prompt=system_prompt)

    agent.output_type = Union[output_type, str]
    agent.output_validator(create_validator(output_type))
    
    return agent

async def run_llm_agent(
    session: Session,
    llm_config_id: int,
    user_prompt: str,
    output_type: Type[BaseModel],
    system_prompt: Optional[str] = None,
    max_tokens: Optional[int] = None,
    max_retries: int = 3,
) -> BaseModel:
    """
    运行LLM Agent的核心封装。
    它处理Agent的获取、运行以及错误处理，并返回符合指定Pydantic模型的结果。
    """
    agent = _get_agent(session, llm_config_id, output_type, system_prompt or '')
    print(f"system_prompt: {system_prompt}")
    last_exception = None
    for attempt in range(max_retries):
        try:
            logger.debug(f"Running agent with prompt (Attempt {attempt + 1}/{max_retries}): {user_prompt}")
            logger.info(f"llm_config_id: {llm_config_id}")
            result = await agent.run(
                user_prompt,
                max_tokens=max_tokens
            )
            logger.debug(f"Agent result: {result}")
            return result.output
        except Exception as e:
            last_exception = e
            logger.warning(f"Agent execution failed on attempt {attempt + 1}/{max_retries} for llm_config_id {llm_config_id}: {e}")

    # If all retries fail
    logger.error(f"Agent execution failed after {max_retries} attempts for llm_config_id {llm_config_id}. Last error: {last_exception}")
    raise ValueError(f"调用LLM服务失败，已重试 {max_retries} 次: {str(last_exception)}")

async def generate_continuation(session: Session, request: ContinuationRequest) -> Dict[str, Any]:
    """根据提供的上下文，生成续写内容。"""
    
    prompt = prompt_service.get_prompt_by_name(session, "standard_continuation")
    if not prompt:
        raise ValueError("未找到 'standard_continuation' 提示词。")

    # 简单的格式化，只使用 content 字段
    formatted_prompt = prompt.template.format(previous_content=request.previous_content)
    
    # 使用通用的生成函数
    result = await run_llm_agent(
        session=session,
        user_prompt=formatted_prompt,
        output_type=BaseModel, # 续写暂时不需要严格的结构
        llm_config_id=request.llm_config_id
    )

    # 假设返回的文本在某个字段中，或者直接就是字符串
    # 这部分可能需要根据实际返回情况调整
    if isinstance(result, BaseModel) and hasattr(result, 'text'):
         return {"content": result.text} # type: ignore
    
    return {"content": str(result)}


async def generate_continuation_streaming(session: Session, request: ContinuationRequest) -> AsyncGenerator[str, None]:
    """以流式方式生成续写内容。"""
    prompt = prompt_service.get_prompt_by_name(session, "standard_continuation")
    if not prompt:
        raise ValueError("未找到 'standard_continuation' 提示词。")

    formatted_prompt = prompt.template.format(previous_content=request.previous_content)
    
    agent = _get_agent(
        session,
        request.llm_config_id,
        output_type=BaseModel,
    )

    try:
        logger.debug(f"正在以流式模式运行 agent，提示词: {formatted_prompt}")
        async with agent.run_stream(
            prompt=formatted_prompt
        ) as result:
            async for text_chunk in result.stream():
                yield text_chunk
    except Exception as e:
        logger.error(
            f"Agent 流式执行在 llm_config_id {request.llm_config_id} 上失败: {e}"
        )
        raise ValueError(f"调用LLM流式服务失败: {str(e)}")
    
    
def create_validator(model_type: Type[BaseModel]) -> Callable[[Any, Any], Awaitable[BaseModel]]:
    '''创建通用的结果验证器'''

    async def validate_result(
        ctx: Any, 
        result: Response, 
    ) -> Response:
        """
        通用结果验证函数
        
        :param ctx: 上下文对象
        :param result: 要验证的结果，可以是模型实例或原始数据
        :param model_type: 目标模型类型
        :return: 验证后的模型实例
        :raises ModelRetry: 验证失败时抛出
        """
        if isinstance(result, model_type):
            return result
        else:
            try:
                print(f"result: {result}")  
                return model_type.model_validate_json(repair_json(result))   #先用json_repair尝试自动修复一波    
            except ValidationError as e:
                err_msg = e.json(include_url=False)
                print(f"Invalid {err_msg}")
                raise ModelRetry(f"Invalid  {err_msg}")
            except Exception as e:
                print("Exception:",e)
                raise ModelRetry(f'Invalid {e}') from e
            
    return validate_result