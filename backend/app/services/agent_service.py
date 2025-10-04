from typing import Awaitable, Callable, Optional, Type, Any, Dict, AsyncGenerator, Union
from fastapi import Response
from json_repair import repair_json
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.settings import ModelSettings
from sqlmodel import Session
from app.services import llm_config_service
from loguru import logger
from app.schemas.ai import ContinuationRequest, AssistantChatRequest
from app.services import prompt_service
from app.db.models import LLMConfig
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
    output_type: Optional[Type[BaseModel]] = None,
    system_prompt: str = '',
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    timeout: float = 64,
    deps_type: Type = str,
    tools: list = None,
) -> Agent:
    """
    根据LLM配置和期望的输出类型，获取一个配置好的LLM Agent实例。
    统一使用 ModelSettings 设置 temperature/max_tokens/timeout（无需按提供商分支分别设置）。
    
    新增参数：
    - deps_type: 依赖注入类型（默认 str）
    - tools: 工具列表（Pydantic AI Tool 对象）
    - output_type: 输出类型（None 表示允许文本和工具调用）
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
        model = OpenAIChatModel(llm_config.model_name, provider=provider)
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
        model = OpenAIChatModel(llm_config.model_name, provider=provider)
    else:
        raise ValueError(f"不支持的提供商类型: {llm_config.provider}")

    # 统一的模型设置
    settings = ModelSettings(
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        extra_body=None,
    )

    # 创建 Agent（支持工具和自定义依赖类型）
    if output_type is None:
        # 不指定 output_type，默认允许文本输出和工具调用
        agent = Agent(
            model, 
            system_prompt=system_prompt, 
            model_settings=settings,
            deps_type=deps_type,
            tools=tools or []
        )
    else:
        # 指定了 output_type，使用 Union[output_type, str] 允许文本回退
        agent = Agent(
            model, 
            system_prompt=system_prompt, 
            model_settings=settings,
            output_type=Union[output_type, str],
            deps_type=deps_type,
            tools=tools or []
        )
        agent.output_validator(create_validator(output_type))
    
    return agent

async def run_agent_with_streaming(agent: Agent, *args, **kwargs):
    """
    使用 agent.iter() 和 node.stream() 迭代获取每个流式响应块内容，
    然后返回最终的完整结果。避免直接返回结果时出现网络波动导致生成失败
    """
    async with agent.run_stream(*args, **kwargs) as stream:
        return await stream.get_output()


async def stream_agent_response(
    agent: Agent,
    user_prompt: str,
    *,
    deps=None,
    message_history: list = None,
    track_tool_calls: bool = True
) -> AsyncGenerator[str, None]:
    """
    通用的流式 Agent 响应生成器，支持工具调用和文本流式输出。
    
    **基于 Pydantic AI 官方示例实现**：
    https://ai.pydantic.dev/agents/#iterating-over-an-agents-graph
    
    工作原理：
    1. 使用 agent.iter() 迭代每个节点（UserPrompt/ModelRequest/CallTools/End）
    2. 对于 ModelRequestNode：检测 FinalResultEvent 后流式输出文本
    3. 对于 CallToolsNode：监听 FunctionToolCallEvent 和 FunctionToolResultEvent
    4. 工具已在 Agent 创建时绑定，会自动执行
    5. 流结束后返回工具调用摘要
    
    Args:
        agent: Pydantic AI Agent 实例（工具已绑定）
        user_prompt: 用户输入的提示词
        deps: 依赖注入的上下文对象
        message_history: 消息历史
        track_tool_calls: 是否在流结束后返回工具调用摘要
        
    Yields:
        增量文本内容或工具调用摘要（JSON 格式）
    """
    from pydantic_ai import (
        FinalResultEvent,
        FunctionToolCallEvent,
        FunctionToolResultEvent,
    )
    
    run_kwargs = {"message_history": message_history} if message_history else {}
    
    tool_calls_info = []
    
    # 使用 iter() 迭代节点（基于官方示例）
    async with agent.iter(user_prompt, deps=deps, **run_kwargs) as run:
        async for node in run:
            # ModelRequestNode - 模型请求节点，可能包含流式文本输出
            
            if Agent.is_model_request_node(node):
                async with node.stream(run.ctx) as request_stream:
                    final_result_found = False
                    async for event in request_stream:
                        # 检测到最终结果开始
                        if isinstance(event, FinalResultEvent):
                            final_result_found = True
                            break
                    
                    # 如果检测到最终结果，流式输出文本（增量模式）
                    if final_result_found:
                        async for output in request_stream.stream_text(delta=True):
                            yield output
            
            # CallToolsNode - 工具调用节点
            elif Agent.is_call_tools_node(node):
                logger.info(node)
                logger.info(f"🔧 [stream_agent_response] 检测到工具调用节点, track_tool_calls={track_tool_calls}")
                if track_tool_calls:
                    async with node.stream(run.ctx) as handle_stream:
                        event_count = 0
                        async for event in handle_stream:
                            event_count += 1
                            logger.info(f"🔍 [stream_agent_response] 收到事件 #{event_count}, 类型: {type(event).__name__}")
                            
                            # 工具调用事件
                            if isinstance(event, FunctionToolCallEvent):
                                logger.info(f" [stream_agent_response] 立即推送工具调用开始: {event.part.tool_name}")
                                logger.info(f"   参数: {event.part.args}")
                                # 立即通知前端工具调用开始
                                notification = f"\n\n__TOOL_CALL_START__:{json.dumps({'tool_name': event.part.tool_name, 'args': event.part.args}, ensure_ascii=False)}"
                                yield notification
                                logger.info(f"✅ [stream_agent_response] 已推送通知到流")
                                
                                tool_calls_info.append({
                                    "tool_name": event.part.tool_name,
                                    "args": event.part.args,
                                    "tool_call_id": event.part.tool_call_id
                                })
                            # 工具返回事件
                            elif isinstance(event, FunctionToolResultEvent):
                                logger.info(f"✅ [stream_agent_response] 工具执行完成: {event.tool_call_id}")
                                logger.info(f"   返回结果: {event.result.content}")
                                # 查找对应的工具调用并添加返回结果
                                for call_info in tool_calls_info:
                                    if call_info.get("tool_call_id") == event.tool_call_id:
                                        call_info["result"] = event.result.content
                                        logger.info(f" [stream_agent_response] 已记录工具结果")
                                        break
                        
                        logger.info(f"🏁 [stream_agent_response] 工具调用节点处理完成，共 {event_count} 个事件")
                        
                        # 工具调用完成后，在后续文本前加上换行，避免紧挨在一起
                        if event_count > 0:
                            yield "\n\n"
                else:
                    logger.warning(f"⚠️ [stream_agent_response] track_tool_calls=False，跳过工具调用追踪")
            
            # End - 结束节点
            elif Agent.is_end_node(node):
                # 运行完成
                pass
    
    # 流结束后，返回工具调用摘要
    if track_tool_calls and tool_calls_info:
        yield f"\n\n__TOOL_SUMMARY__:{json.dumps({'type': 'tools_executed', 'tools': tool_calls_info}, ensure_ascii=False)}"

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
    
    logger.info(f"system_prompt: {system_prompt}")
    logger.info(f"user_prompt: {user_prompt}")
    
    last_exception = None
    for attempt in range(max_retries):
        try:
            response=await run_agent_with_streaming(agent, user_prompt, deps=deps)

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




async def generate_assistant_chat_streaming(
    session: Session,
    request: AssistantChatRequest,
    system_prompt: str,
    tools: list,  #  直接接受工具函数列表
    deps,  #  依赖上下文（AssistantDeps 实例）
    track_stats: bool = True
) -> AsyncGenerator[str, None]:
    """
    灵感助手专用流式对话生成。
    
    参数：
    - request: AssistantChatRequest（包含对话历史、卡片上下文等）
    - system_prompt: 系统提示词
    - tools: 工具函数列表（直接传函数，符合 Pydantic AI 标准用法）
    - deps: 工具依赖上下文（AssistantDeps 实例）
    - track_stats: 是否统计 token 使用
    """
    
    # 直接使用前端发送的上下文和用户输入
    parts = []
    
    # 1. 项目上下文信息（包含结构树、统计、操作历史等）
    if request.context_info:
        parts.append(request.context_info)
    
    # 2. 用户当前输入
    if request.user_prompt:
        parts.append(f"\n**用户说**：{request.user_prompt}")
    
    final_user_prompt = "\n\n".join(parts) if parts else "（用户未输入文字，可能是想查看项目信息或需要帮助）"
    
    logger.info(f"灵感助手 system_prompt: {system_prompt}...")
    logger.info(f"灵感助手 final_user_prompt: {final_user_prompt}...")
    
    # 限额预检
    if track_stats:
        ok, reason = _precheck_quota(session, request.llm_config_id, _calc_input_tokens(system_prompt, final_user_prompt), need_calls=1)
        if not ok:
            raise ValueError(f"LLM 配额不足:{reason}")
    
    # 创建 Agent（带工具）
    from app.services.assistant_tools.pydantic_ai_tools import AssistantDeps
    
    # 直接在创建时传入工具列表（Pydantic AI 推荐方式）
    agent = _get_agent(
        session=session,
        llm_config_id=request.llm_config_id,
        output_type=None,  # 允许工具调用
        system_prompt=system_prompt,
        temperature=request.temperature or 0.7,
        max_tokens=request.max_tokens or 4096,
        timeout=request.timeout or 60,
        deps_type=AssistantDeps,
        tools=tools  # 直接传入工具函数列表
    )
    
    # 流式生成响应
    accumulated = ""
    
    try:
        async for chunk in stream_agent_response(
            agent,
            final_user_prompt,
            deps=deps,  # 传入依赖上下文
            track_tool_calls=True
        ):
            accumulated += chunk
            yield chunk
        
    except asyncio.CancelledError:
        if track_stats:
            in_tokens = _calc_input_tokens(system_prompt, final_user_prompt)
            out_tokens = _estimate_tokens(accumulated)
            _record_usage(session, request.llm_config_id, in_tokens, out_tokens, calls=1, aborted=True)
        return
    except Exception as e:
        logger.error(f"灵感助手生成失败: {e}")
        # 即使失败也要发送错误摘要，让前端清除"正在调用工具"状态
        yield f"\n\n__ERROR__:{json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}"
        raise
    
    # 统计
    if track_stats:
        try:
            in_tokens = _calc_input_tokens(system_prompt, final_user_prompt)
            out_tokens = _estimate_tokens(accumulated)
            _record_usage(session, request.llm_config_id, in_tokens, out_tokens, calls=1, aborted=False)
        except Exception as stat_e:
            logger.warning(f"记录灵感助手统计失败: {stat_e}")


async def generate_continuation_streaming(session: Session, request: ContinuationRequest, system_prompt: str, track_stats: bool = True) -> AsyncGenerator[str, None]:
    """以流式方式生成续写内容。system_prompt 由外部显式传入。"""
    # 组装用户消息
    user_prompt_parts = []
    
    # 1. 添加上下文信息（引用上下文 + 事实子图）
    context_info = (getattr(request, 'context_info', None) or '').strip()
    if context_info:
        # 检测 context_info 是否已包含结构化标记（如【引用上下文】、【上文】等）
        has_structured_marks = any(mark in context_info for mark in ['【引用上下文】', '【上文】', '【需要润色', '【需要扩写'])
        
        if has_structured_marks:
            # 已经是结构化的上下文，直接使用，不再额外包裹
            user_prompt_parts.append(context_info)
        else:
            # 未结构化的上下文（老格式），添加标记
            user_prompt_parts.append(f"【参考上下文】\n{context_info}")
    
    # 2. 添加已有章节内容（仅当 previous_content 非空时）
    previous_content = (request.previous_content or '').strip()
    if previous_content:
        user_prompt_parts.append(f"【已有章节内容】\n{previous_content}")
        
        # 添加字数统计信息
        existing_word_count = getattr(request, 'existing_word_count', None)
        if existing_word_count is not None:
            user_prompt_parts.append(f"（已有内容字数：{existing_word_count} 字）")
        
        # 续写指令
        if getattr(request, 'append_continuous_novel_directive', True):
            user_prompt_parts.append("【指令】请接着上述内容继续写作，保持文风和剧情连贯。直接输出小说正文。")
    else:
        # 新写模式或润色/扩写模式（previous_content 为空）
        # 只在需要时添加指令
        if getattr(request, 'append_continuous_novel_directive', True):
            # 如果 context_info 中有续写相关标记，说明是续写场景
            if context_info and '【已有章节内容】' in context_info:
                user_prompt_parts.append("【指令】请接着上述内容继续写作，保持文风和剧情连贯。直接输出小说正文。")
            else:
                user_prompt_parts.append("【指令】请开始创作新章节。直接输出小说正文。")
    
    user_prompt = "\n\n".join(user_prompt_parts)
    
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
            if model_type is BaseModel or model_type is str: 
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

        return parsed 

    return validate_result