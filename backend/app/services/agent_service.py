from typing import Awaitable, Callable, Optional, Type, Any, Dict, AsyncGenerator, Union
from fastapi import Response
from json_repair import repair_json
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.settings import ModelSettings
from sqlmodel import Session
from app.services import llm_config_service
from loguru import logger
from app.schemas.ai import ContinuationRequest
from app.services import prompt_service
import asyncio
import json

# 上下文装配
from app.services.context_service import assemble_context, ContextAssembleParams
# 导入需要校验的模型
from app.schemas.wizard import StageLine, ChapterOutline, Chapter


def _get_agent(
    session: Session,
    llm_config_id: int,
    output_type: Type[BaseModel],
    system_prompt: str = '',
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    timeout: float = 64,
) -> Agent:
    """
    根据LLM配置和期望的输出类型，获取一个配置好的LLM Agent实例。
    统一使用 ModelSettings 设置 temperature/max_tokens/timeout（无需按提供商分支分别设置）。
    """
    llm_config = llm_config_service.get_llm_config(session, llm_config_id)
    if not llm_config:
        raise ValueError(f"LLM配置不存在，ID: {llm_config_id}")

    if not llm_config.api_key:
        raise ValueError(f"未找到LLM配置 {llm_config.display_name or llm_config.model_name} 的API密钥")

    # Provider & Model 创建（不再在此处设置温度/超时）
    if llm_config.provider == "openai":
        provider_config = {"api_key": llm_config.api_key}
        if llm_config.api_base:
            provider_config["base_url"] = llm_config.api_base
        provider = OpenAIProvider(**provider_config)
        model = OpenAIModel(llm_config.model_name, provider=provider)
    elif llm_config.provider == "anthropic":
        provider_config = {"api_key": llm_config.api_key}
        if llm_config.api_base:
            provider_config["base_url"] = llm_config.api_base
        provider = AnthropicProvider(**provider_config)
        model = AnthropicModel(llm_config.model_name, provider=provider)
    elif llm_config.provider == "custom":
        provider_config = {"api_key": llm_config.api_key}
        if llm_config.api_base:
            provider_config["base_url"] = llm_config.api_base
        provider = OpenAIProvider(**provider_config)
        model = OpenAIModel(llm_config.model_name, provider=provider)
    else:
        raise ValueError(f"不支持的提供商类型: {llm_config.provider}")

    # 统一的模型设置
    settings = ModelSettings(
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        extra_body=None,
    )

    agent = Agent(model, system_prompt=system_prompt, model_settings=settings,deps_type=str)
    agent.output_type = Union[output_type, str]
    agent.output_validator(create_validator(output_type))
    return agent

async def run_agent_with_streaming(agent: Agent, *args, **kwargs):
    """
    使用 agent.iter() 和 node.stream() 迭代获取每个流式响应块内容，
    然后返回最终的完整结果。避免直接返回结果时出现网络波动导致生成失败
    """
    async with agent.run_stream(*args, **kwargs) as stream:
        return await stream.get_output()

async def run_llm_agent(
    session: Session,
    llm_config_id: int,
    user_prompt: str,
    output_type: Type[BaseModel],
    system_prompt: Optional[str] = None,
    deps: str = "",
    max_tokens: Optional[int] = None,
    max_retries: int = 3,
    temperature: Optional[float] = None,
    timeout: Optional[float] = None,
) -> BaseModel:
    """
    运行LLM Agent的核心封装。
    支持温度/最大tokens/超时（通过 ModelSettings 注入）。
    """
    agent = _get_agent(
        session,
        llm_config_id,
        output_type,
        system_prompt or '',
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    logger.info(f"system_prompt\n {system_prompt}")
    last_exception = None
    for attempt in range(max_retries):
        try:
            logger.debug(f"Running agent with prompt (Attempt {attempt + 1}/{max_retries}): {user_prompt}")
            logger.info(f"llm_config_id: {llm_config_id}")
            # max_tokens 已在 ModelSettings 中设置
            # response = (await agent.run(user_prompt,deps=deps)).output
            logger.info(f"system_prompt长度:{len(system_prompt)},user_prompt长度:{len(user_prompt)},总长度:{len(system_prompt)+len(user_prompt)}")
            response = await run_agent_with_streaming(agent, user_prompt, deps=deps) #为避免生成内容过长时容易出现网络中断问题，这里都用流式结果，只不过run_agent_with_streaming会将流式输出结果全部接收完成后整合起来返回
            
            return response
        except asyncio.CancelledError:
            logger.info("LLM 调用被取消（CancelledError），立即中止，不再重试。")
            raise
        except Exception as e:
            last_exception = e
            logger.warning(f"Agent execution failed on attempt {attempt + 1}/{max_retries} for llm_config_id {llm_config_id}: {e}")

    logger.error(f"Agent execution failed after {max_retries} attempts for llm_config_id {llm_config_id}. Last error: {last_exception}")
    raise ValueError(f"调用LLM服务失败，已重试 {max_retries} 次: {str(last_exception)}")

async def generate_continuation(session: Session, request: ContinuationRequest, system_prompt: str) -> Dict[str, Any]:
    """根据提供的上下文，生成续写内容。system_prompt 由外部显式传入。"""
    # 若前端已提供上下文，则直接使用；否则回退到服务端装配
    supplied_ctx = (getattr(request, 'current_draft_tail', None) or '').strip()
    if supplied_ctx:
        user_prompt = (
            f"【写作上下文】\n{supplied_ctx}\n\n"
            f"请基于以上上下文继续写下去。不要编号，不要小标题，不要列表格式；直接输出连续的小说正文。"
        )
    else:
        ctx = assemble_context(session, ContextAssembleParams(
            project_id=getattr(request, 'project_id', None),
            volume_number=getattr(request, 'volume_number', None),
            chapter_number=getattr(request, 'chapter_number', None),
            participants=getattr(request, 'participants', None),
            current_draft_tail=request.previous_content,
        ))
        user_prompt = (
            f"【写作上下文】\n{ctx.to_system_prompt_block()}\n\n"
            f"请基于以上上下文继续写下去。不要编号，不要小标题，不要列表格式；直接输出连续的小说正文。"
        )
    
    

    result = await run_llm_agent(
        session=session,
        user_prompt=user_prompt,
        output_type=BaseModel,
        llm_config_id=request.llm_config_id,
        system_prompt=system_prompt,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        timeout=request.timeout,
    )

    if isinstance(result, BaseModel) and hasattr(result, 'text'):
         return {"content": result.text}  # type: ignore
    return {"content": str(result)}

async def generate_continuation_streaming(session: Session, request: ContinuationRequest, system_prompt: str) -> AsyncGenerator[str, None]:
    """以流式方式生成续写内容。system_prompt 由外部显式传入。"""
    supplied_ctx = (getattr(request, 'current_draft_tail', None) or '').strip()
    if supplied_ctx:
        user_prompt = (
            f"【写作上下文】\n{supplied_ctx}\n\n"
            f"请基于以上上下文继续创作。直接输出连续的小说正文。"
        )
    else:
        ctx = assemble_context(session, ContextAssembleParams(
            project_id=getattr(request, 'project_id', None),
            volume_number=getattr(request, 'volume_number', None),
            chapter_number=getattr(request, 'chapter_number', None),
            participants=getattr(request, 'participants', None),
            current_draft_tail=request.previous_content,
        ))
        user_prompt = (
            f"【写作上下文】\n{ctx.to_system_prompt_block()}\n\n"
            f"请基于以上上下文继续创作。直接输出连续的小说正文。"
        )

    logger.info(f"user_prompt: {user_prompt}")
    
    logger.info(f"===========system_prompt长度:{len(system_prompt)},user_prompt长度:{len(user_prompt)},总长度:{len(system_prompt)+len(user_prompt)}=============")
    
    agent = _get_agent(
        session,
        request.llm_config_id,
        output_type=BaseModel,
        system_prompt=system_prompt,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        timeout=request.timeout,
    )

    try:
        logger.debug(f"正在以流式模式运行 agent")
        async with agent.run_stream(user_prompt) as result:
            accumulated: str = ""
            async for text_chunk in result.stream():
                try:
                    chunk = str(text_chunk)
                except Exception:
                    chunk = ""
                if not chunk:
                    continue
                # 若返回的是累计文本，只发送新增差量
                if accumulated and chunk.startswith(accumulated):
                    delta = chunk[len(accumulated):]
                else:
                    # 回退：无法判断前缀时，直接把本次 chunk 作为增量
                    delta = chunk
                if delta:
                    yield delta
                if len(chunk) > len(accumulated):
                    accumulated = chunk
    except asyncio.CancelledError:
        logger.info("流式 LLM 调用被取消（CancelledError），停止推送。")
        return
    except Exception as e:
        logger.error(f"流式 LLM 调用失败: {e}")
        raise


def create_validator(model_type: Type[BaseModel]) -> Callable[[Any, Any], Awaitable[BaseModel]]:
    '''创建通用的结果验证器'''

    async def validate_result(
        ctx: Any,
        result: Response,
    ) -> Response:
        """
        通用结果验证函数
        """
        try:
            if model_type is BaseModel or model_type is str:  # type: ignore[comparison-overlap]
                return result
        except Exception:
            return result

        # 尝试解析为目标模型
        parsed: BaseModel
        if isinstance(result, model_type):
            parsed = result
        else:
            try:
                print(f"result: {result}")
                parsed = model_type.model_validate_json(repair_json(result))
            except ValidationError as e:
                err_msg = e.json(include_url=False)
                print(f"Invalid {err_msg}")
                raise ModelRetry(f"Invalid  {err_msg}")
            except Exception as e:
                print("Exception:", e)
                raise ModelRetry(f'Invalid {e}') from e

        # === 针对 StageLine/ChapterOutline/Chapter 的实体存在性校验 ===
        try:
            # 解析 deps 中的实体名称集合
            all_names: set[str] = set()
            try:
                deps_obj = json.loads(getattr(ctx, 'deps', '') or '{}')
                for nm in (deps_obj.get('all_entity_names') or []):
                    if isinstance(nm, str) and nm.strip():
                        all_names.add(nm.strip())
            except Exception:
                all_names = set()
                
            

            def _check_entity_list(obj: Any) -> list[str]:
                bad: list[str] = []
                try:
                    items = getattr(obj, 'entity_list', None)
                    if isinstance(items, list):
                        for it in items:
                            nm = getattr(it, 'name', None)
                            if isinstance(nm, str) and nm.strip():
                                if all_names and nm.strip() not in all_names:
                                    bad.append(nm.strip())
                except Exception:
                    pass
                return bad

            invalid: list[str] = []
            if isinstance(parsed, (StageLine, ChapterOutline, Chapter)):
                logger.info(f"开始校验实体,all_names: {all_names}")
                invalid = _check_entity_list(parsed)
       

            if invalid:
                raise ModelRetry(f"实体不存在: {', '.join(sorted(set(invalid)))}，请仅从提供的实体列表中选择")
        except ModelRetry:
            raise
        except Exception:
            # 校验过程中不应阻塞主流程，如解析失败则忽略
            pass

        return parsed  # type: ignore[return-value]

    return validate_result