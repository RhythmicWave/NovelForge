from typing import Awaitable, Callable, Optional, Type, Any, Dict, AsyncGenerator, Union
from fastapi import Response
from json_repair import repair_json
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
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
import re


_TOKEN_REGEX = re.compile(
    r"""
    ([A-Za-z]+)               # 英文单词（连续字母算 1）
    |([0-9])                 # 1个数字算 1
    |([\u4E00-\u9FFF])       # 单个中文汉字算 1
    |(\S)                     # 其它非空白符号/标点算 1
    """,
    re.VERBOSE,
)

def _estimate_tokens(text: str) -> int:
    """按规则估算 token：
    - 1 个中文 = 1
    - 1 个英文单词 = 1
    - 1 个数字 = 1
    - 1 个符号 = 1
    空白不计。
    """
    if not text:
        return 0
    try:
        return sum(1 for _ in _TOKEN_REGEX.finditer(text))
    except Exception:
        # 退化：按非空白字符计数
        return sum(1 for ch in (text or "") if not ch.isspace())

from app.services import llm_config_service as _llm_svc

def _calc_input_tokens(system_prompt: Optional[str], user_prompt: Optional[str]) -> int:
    sys_part = system_prompt or ""
    usr_part = user_prompt or ""
    return _estimate_tokens(sys_part+usr_part) 


def _precheck_quota(session: Session, llm_config_id: int, input_tokens: int, need_calls: int = 1) -> None:
    ok, reason = _llm_svc.can_consume(session, llm_config_id, input_tokens, 0, need_calls)
    return ok,reason


def _record_usage(session: Session, llm_config_id: int, input_tokens: int, output_tokens: int, calls: int = 1, aborted: bool = False) -> None:
    try:
        _llm_svc.accumulate_usage(session, llm_config_id, max(0, input_tokens), max(0, output_tokens), max(0, calls), aborted=aborted)
    except Exception as stat_e:
        logger.warning(f"记录 LLM 统计失败: {stat_e}")

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
    print(f"=======llm_config.provider:{llm_config.provider}=========")
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
    elif llm_config.provider == "google":

        provider = GoogleProvider(api_key=llm_config.api_key)
        model = GoogleModel(llm_config.model_name, provider=provider)
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
    track_stats: bool = True,
) -> BaseModel:
    """
    运行LLM Agent的核心封装。
    支持温度/最大tokens/超时（通过 ModelSettings 注入）。
    """
    # 限额预检（按估算的输入 tokens + 1 次调用）
    if track_stats:
        ok, reason = _precheck_quota(session, llm_config_id, _calc_input_tokens(system_prompt, user_prompt), need_calls=1)
        if not ok:
            raise ValueError(f"LLM 配额不足:{reason}")

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
            len_system_prompt = _estimate_tokens(system_prompt)
            len_user_prompt = _estimate_tokens(user_prompt)
            len_total = len_system_prompt + len_user_prompt
            logger.info(f"system_prompt token长度:{len_system_prompt},user_prompt token长度:{len_user_prompt},总token 长度:{len_total}")
            response = await run_agent_with_streaming(agent, user_prompt, deps=deps) #为避免生成内容过长时容易出现网络中断问题，这里都用流式结果，只不过run_agent_with_streaming会将流式输出结果全部接收完成后整合起来返回

            # 统计：输入/输出 tokens 与调用次数
            if track_stats:
                in_tokens = _calc_input_tokens(system_prompt, user_prompt)
                try:
                    out_text = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
                except Exception:
                    out_text = str(response)
                out_tokens = _estimate_tokens(out_text)
                _record_usage(session, llm_config_id, in_tokens, out_tokens, calls=1, aborted=False)
            return response
        except asyncio.CancelledError:
            logger.info("LLM 调用被取消（CancelledError），立即中止，不再重试。")
            if track_stats:
                in_tokens = _calc_input_tokens(system_prompt, user_prompt)
                _record_usage(session, llm_config_id, in_tokens, 0, calls=1, aborted=True)
            raise
        except Exception as e:
            last_exception = e
            logger.warning(f"Agent execution failed on attempt {attempt + 1}/{max_retries} for llm_config_id {llm_config_id}: {e}")

    logger.error(f"Agent execution failed after {max_retries} attempts for llm_config_id {llm_config_id}. Last error: {last_exception}")
    raise ValueError(f"调用LLM服务失败，已重试 {max_retries} 次: {str(last_exception)}")


async def generate_continuation_streaming(session: Session, request: ContinuationRequest, system_prompt: str, track_stats: bool = True) -> AsyncGenerator[str, None]:
    """以流式方式生成续写内容。system_prompt 由外部显式传入。"""
    supplied_ctx = (getattr(request, 'current_draft_tail', None) or '').strip()
    directive = "请基于以上上下文继续创作。直接输出连续的小说正文。" if getattr(request, 'append_continuous_novel_directive', True) else ""
    if supplied_ctx:
        user_prompt = (
            f"【上下文】\n{supplied_ctx}\n\n"
            f"{directive}"
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
            f"【上下文】\n{ctx.to_system_prompt_block()}\n\n"
            f"{directive}"
        )

    logger.info(f"system_prompt: {system_prompt}")
    logger.info(f"user_prompt: {user_prompt}")
    
    logger.info(f"===========system_prompt长度:{len(system_prompt)},user_prompt长度:{len(user_prompt)},总长度:{len(system_prompt)+len(user_prompt)}=============")
    
    # 限额预检
    if track_stats:
        ok, reason = _precheck_quota(session, request.llm_config_id, _calc_input_tokens(system_prompt, user_prompt), need_calls=1)
        if not ok:
            raise ValueError(f"LLM 配额不足:{reason}")

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
            # 统计用：累积输出字符数
            out_chars: int = 0
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
                    out_chars += len(delta)
                    yield delta
                if len(chunk) > len(accumulated):
                    accumulated = chunk
    except asyncio.CancelledError:
        logger.info("流式 LLM 调用被取消（CancelledError），停止推送。")
        if track_stats:
            in_tokens = _calc_input_tokens(system_prompt, user_prompt)
            out_tokens = _estimate_tokens(accumulated)
            _record_usage(session, request.llm_config_id, in_tokens, out_tokens, calls=1, aborted=True)
        return
    except Exception as e:
        logger.error(f"流式 LLM 调用失败: {e}")
        raise
    # 正常结束后统计
    try:
        if track_stats:
            in_tokens = _calc_input_tokens(system_prompt, user_prompt)
            out_tokens = _estimate_tokens(accumulated)
            _record_usage(session, request.llm_config_id, in_tokens, out_tokens, calls=1, aborted=False)
    except Exception as stat_e:
        logger.warning(f"记录 LLM 流式统计失败: {stat_e}")


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