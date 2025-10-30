from typing import Awaitable, Callable, Optional, Type, Any, Dict, AsyncGenerator, Union
from fastapi import Response
from json_repair import repair_json
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent, ModelResponse, ModelRetry
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
import re
import os
from datetime import datetime

# 导入需要校验的模型
from app.schemas.wizard import StageLine, ChapterOutline, Chapter
import re

# 从环境变量读取工具调用最大重试次数，默认为 3
MAX_TOOL_CALL_RETRIES = int(os.getenv('MAX_TOOL_CALL_RETRIES', '3'))

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


def check_tool_call(parts: list,is_in_retry_state: bool) -> bool:
    need_tool_call=is_in_retry_state
    include_tool_call=False
    for part in parts:
        if part.part_kind=="text":
            if re.search(r"<notify>[\w\-]+</notify>", part.content):
                need_tool_call=True
    if need_tool_call:
        for part in parts:
            if part.part_kind=="tool-call":
                include_tool_call=True
                break
    return (not need_tool_call) or include_tool_call

from pydantic_ai import (
        FinalResultEvent,
        FunctionToolCallEvent,
        FunctionToolResultEvent,
    )
from pydantic_ai.messages import (
    ModelRequest,
    RetryPromptPart,
    ToolCallPart
)

from pydantic_ai import _agent_graph


async def execute_react_tool(
    tool_name: str,
    tool_args: Dict[str, Any],
    deps: Any,
    tools_map: Dict[str, Callable]
) -> Dict[str, Any]:
    """
    执行 ReAct 模式的工具调用
    
    Args:
        tool_name: 工具名称
        tool_args: 工具参数
        deps: 依赖上下文
        tools_map: 工具函数映射表
        
    Returns:
        工具执行结果 {"tool_name": str, "args": dict, "result": Any, "success": bool, "error": Optional[str]}
    """
    logger.info(f"🔧 [ReAct] 执行工具: {tool_name}")
    logger.info(f"   参数: {json.dumps(tool_args, ensure_ascii=False)[:200]}...")
    
    # 验证工具名称
    if tool_name not in tools_map:
        error_msg = f"未知工具: {tool_name}"
        logger.error(f"❌ [ReAct] {error_msg}")
        return {
            "tool_name": tool_name,
            "args": tool_args,
            "success": False,
            "error": error_msg
        }
    
    try:
        tool_func = tools_map[tool_name]
        
        # 创建简单的上下文对象（兼容 Pydantic AI 工具签名）
        class SimpleContext:
            def __init__(self, deps):
                self.deps = deps
        
        ctx = SimpleContext(deps=deps)
        
        # 调用工具（检查是否需要 ctx 参数）
        import inspect
        sig = inspect.signature(tool_func)
        if 'ctx' in sig.parameters:
            result = tool_func(ctx, **tool_args)
        else:
            result = tool_func(**tool_args)
        
        logger.info(f"✅ [ReAct] 工具执行成功: {tool_name}")
        
        return {
            "tool_name": tool_name,
            "args": tool_args,
            "result": result,
            "success": True
        }
    
    except Exception as e:
        error_msg = f"工具执行失败: {str(e)}"
        logger.error(f"❌ [ReAct] {error_msg}", exc_info=True)
        return {
            "tool_name": tool_name,
            "args": tool_args,
            "success": False,
            "error": error_msg
        }


async def process_react_text(
    text: str,
    react_accumulated_text: str,
    react_processed_calls: list,
    tool_calls_info: list,
    deps: Any,
    react_tools_map: Dict[str, Callable]
) -> AsyncGenerator[Union[str, tuple], None]:
    """
    处理 ReAct 模式的文本：检测工具调用、执行工具、输出文本
    
    Args:
        text: 当前文本块
        react_accumulated_text: 累积的文本
        react_processed_calls: 已处理的工具调用位置列表
        tool_calls_info: 工具调用信息列表
        deps: 依赖上下文
        react_tools_map: 工具函数映射表
        
    Yields:
        - str: 协议标记和文本内容
        - tuple: 最后一个 yield 返回 (updated_accumulated_text, new_tool_count) 元组
    """
    # 累积文本
    react_accumulated_text += text
    new_tool_count = 0
    
    # 检测并处理工具调用
    tool_call_pattern = re.compile(r'<tool_call>(.*?)</tool_call>', re.DOTALL)
    
    for match in tool_call_pattern.finditer(react_accumulated_text):
        match_key = (match.start(), match.end())
        
        # 避免重复处理
        if match_key in react_processed_calls:
            continue
        
        react_processed_calls.append(match_key)
        logger.info(f"[ReAct] 检测到工具调用 (位置 {match.start()}-{match.end()})")
        
        # 通知前端工具调用开始
        yield "\n\n__TOOL_CALL_DETECTED__\n\n"
        
        # 解析并执行工具
        try:
            tool_json = match.group(1).strip()
            try:
                tool_call_data = json.loads(tool_json)
            except json.JSONDecodeError:
                logger.warning(f"[ReAct] JSON 解析失败，尝试自动修复...")
                repaired_json = repair_json(tool_json)
                tool_call_data = json.loads(repaired_json)
                logger.info(f"[ReAct] JSON 修复成功")
            
            tool_name = tool_call_data.get("name")
            tool_args = tool_call_data.get("args", {})
            
            # 执行工具
            tool_result = await execute_react_tool(
                tool_name=tool_name,
                tool_args=tool_args,
                deps=deps,
                tools_map=react_tools_map
            )
            
            # 通知前端工具执行完成
            yield f"__TOOL_EXECUTED__:{json.dumps(tool_result, ensure_ascii=False)}\n\n"
            
            # 记录工具调用
            tool_calls_info.append(tool_result)
            new_tool_count += 1
            
        except Exception as e:
            error_msg = f"工具调用处理失败: {str(e)}"
            logger.error(f"[ReAct] {error_msg}", exc_info=True)
            yield f"\n\n❌ {error_msg}\n\n"
    
    # 输出文本（前端会过滤掉 <tool_call> 标记）
    yield text
    
    # 最后 yield 更新后的累积文本和新工具数量
    yield (react_accumulated_text, new_tool_count)


async def stream_agent_response(
    agent: Agent,
    user_prompt: str,
    *,
    deps=None,
    message_history: list = None,
    track_tool_calls: bool = True,
    max_tool_call_retries: int = None,
    use_react_mode: bool = False,
    react_tools_map: Optional[Dict[str, Callable]] = None
) -> AsyncGenerator[str, None]:
    """
    通用的流式 Agent 响应生成器，支持工具调用和文本流式输出。
    
    **基于 Pydantic AI 官方文档实现**：
    - 自动迭代：https://ai.pydantic.dev/agents/#iterating-over-an-agents-graph
    - 手动迭代：https://ai.pydantic.dev/agents/#using-next-manually
    - 图节点：https://ai.pydantic.dev/graph/
    
    工作原理：
    1. 使用手动迭代模式 run.next() 逐个处理节点
    2. 对于 ModelRequestNode：
       - 检测 FinalResultEvent 后流式输出文本
       - **ReAct 模式**：实时检测 <tool_call>...</tool_call> 并手动执行工具
    3. 对于 CallToolsNode（仅标准模式）：
       - 检测模型是否正确调用了工具（通过 check_tool_call）
       - 如果未正确调用，注入重试提示并跳过节点，最多重试 max_tool_call_retries 次
       - 如果正确调用，监听工具执行事件并流式推送状态
    4. 流结束后返回工具调用摘要
    5. **ReAct 模式**：工具执行后注入结果节点，继续迭代让 agent 基于结果生成
    
    Args:
        agent: Pydantic AI Agent 实例（标准模式需绑定工具，ReAct 模式无需绑定）
        user_prompt: 用户输入的提示词
        deps: 依赖注入的上下文对象
        message_history: 消息历史
        track_tool_calls: 是否在流结束后返回工具调用摘要
        max_tool_call_retries: 工具调用失败时的最大重试次数
        use_react_mode: 是否使用 ReAct 模式（文本格式工具调用）
        react_tools_map: ReAct 模式的工具函数映射表
        
    Yields:
        增量文本内容或工具调用摘要（JSON 格式）
    """
    
    
    run_kwargs = {"message_history": message_history} if message_history else {}
    
    # 使用全局配置的最大重试次数（如果未传入）
    if max_tool_call_retries is None:
        max_tool_call_retries = MAX_TOOL_CALL_RETRIES
    
    tool_calls_info = []
    tool_call_retry_count = 0  # 工具调用重试计数器
    
    is_in_retry_state = False
    
    # ReAct 模式相关变量
    react_accumulated_text = ""  # ReAct 模式累积的文本
    react_processed_calls = []  # 已处理的工具调用（存储位置）
    react_last_tool_count = 0  # 上一轮的工具调用总数（用于计算本轮新增）
    
    # 使用手动迭代模式（基于官方文档）
    async with agent.iter(user_prompt, deps=deps, **run_kwargs) as run:
        node = run.next_node
        while True:
            # 手动获取下一个节点
            node = await run.next(node)
            
            # 迭代结束
            if node is None:
                break
            
            logger.info(f"📍 [stream_agent_response] 当前节点: {type(node).__name__}")
            
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
                        # ReAct 模式：累积文本并实时检测工具调用
                        if use_react_mode and react_tools_map:
                            async for output in request_stream.stream_text(delta=True):
                                # 使用统一的 process_react_text 函数处理文本
                                async for chunk in process_react_text(
                                    text=output,
                                    react_accumulated_text=react_accumulated_text,
                                    react_processed_calls=react_processed_calls,
                                    tool_calls_info=tool_calls_info,
                                    deps=deps,
                                    react_tools_map=react_tools_map
                                ):
                                    # 最后一个返回值是 tuple，包含更新后的累积文本
                                    if isinstance(chunk, tuple):
                                        react_accumulated_text, _ = chunk
                                    else:
                                        yield chunk
                        
                        # 标准模式：直接流式输出
                        else:
                            async for output in request_stream.stream_text(delta=True):
                                yield output
                
                # ReAct 模式：如果有新的工具调用，注入工具结果节点并继续迭代
                if use_react_mode and react_processed_calls and final_result_found:
                    # 计算本轮新增的工具调用数量（当前总数 - 上一轮总数）
                    current_tool_count = len(tool_calls_info)
                    new_tools_count = current_tool_count - react_last_tool_count
                    
                    if new_tools_count > 0:
                        logger.info(f"[ReAct] 本轮新增 {new_tools_count} 个工具调用，注入结果节点")
                        
                        # 构建工具结果摘要文本
                        tool_results_text = "\n\n**工具执行结果**：\n\n"
                        for tool_info in tool_calls_info[-new_tools_count:]:
                            if tool_info.get('success'):
                                tool_results_text += f"✅ {tool_info['tool_name']}\n"
                                tool_results_text += f"```json\n{json.dumps(tool_info['result'], ensure_ascii=False, indent=2)}\n```\n\n"
                            else:
                                tool_results_text += f"❌ {tool_info['tool_name']}: {tool_info.get('error', '未知错误')}\n\n"
                        
                        tool_results_text += "请基于以上工具调用结果继续回答用户。\n"
                        
                        logger.info(f"[ReAct] 工具结果摘要:\n{tool_results_text[:300]}...")
                        
                        # 创建新的请求节点（注入工具结果）
                
                        node = _agent_graph.ModelRequestNode(
                            request=ModelRequest(parts=[
                                RetryPromptPart(
                                    content=tool_results_text,
                                    timestamp=datetime.now()
                                )
                            ])
                        )
                        
                        
                        # 更新上一轮工具数量
                        react_last_tool_count = current_tool_count
                        
                        # 清空累积文本和处理记录，准备下一轮
                        react_accumulated_text = ""
                        react_processed_calls = []
                        
                        logger.info(f"[ReAct] 已注入工具结果节点，继续下一轮迭代")
                        continue  # 继续迭代，让 agent 基于工具结果生成
            
            # CallToolsNode - 工具调用节点
            elif Agent.is_call_tools_node(node):
                logger.info(node)
                parts = node.model_response.parts
                
                # 🔑 ReAct 模式特殊处理：CallToolsNode 可能只包含 TextPart
                # 在 ReAct 模式下，LLM 不使用原生工具调用，而是输出文本格式的 <tool_call>
                if use_react_mode:
                    # 提取所有 TextPart
                    text_parts = [p.content for p in parts if p.part_kind == 'text']
                    if text_parts:
                        logger.info(f"[ReAct] CallToolsNode 包含 {len(text_parts)} 个 TextPart，处理工具调用")
                        
                        for text in text_parts:
                            # 使用统一的 process_react_text 函数处理文本
                            async for chunk in process_react_text(
                                text=text,
                                react_accumulated_text=react_accumulated_text,
                                react_processed_calls=react_processed_calls,
                                tool_calls_info=tool_calls_info,
                                deps=deps,
                                react_tools_map=react_tools_map
                            ):
                                # 最后一个返回值是 tuple，包含更新后的累积文本
                                if isinstance(chunk, tuple):
                                    react_accumulated_text, _ = chunk
                                else:
                                    yield chunk
                        
                        # 检查是否需要注入工具结果节点（与 ModelRequestNode 后的逻辑相同）
                        if react_processed_calls:
                            current_tool_count = len(tool_calls_info)
                            new_tools_count = current_tool_count - react_last_tool_count
                            
                            if new_tools_count > 0:
                                logger.info(f"[ReAct] CallToolsNode 中执行了 {new_tools_count} 个工具，注入结果节点")
                                
                                tool_results_text = "\n\n**工具执行结果**：\n\n"
                                for tool_info in tool_calls_info[-new_tools_count:]:
                                    if tool_info.get('success'):
                                        tool_results_text += f"✅ {tool_info['tool_name']}\n"
                                        tool_results_text += f"```json\n{json.dumps(tool_info['result'], ensure_ascii=False, indent=2)}\n```\n\n"
                                    else:
                                        tool_results_text += f"❌ {tool_info['tool_name']}: {tool_info.get('error', '未知错误')}\n\n"
                                
                                tool_results_text += "请基于以上工具调用结果继续回答用户。\n"
                                
                       
                                node = _agent_graph.ModelRequestNode(
                                    request=ModelRequest(parts=[
                                        RetryPromptPart(
                                            content=tool_results_text,
                                            timestamp=datetime.now()
                                        )
                                    ])
                                )
                                
                                react_last_tool_count = current_tool_count
                                react_accumulated_text = ""
                                react_processed_calls = []
                                
                                logger.info(f"[ReAct] 已注入工具结果节点，继续迭代")
                                continue
                    
                    # 没有工具调用或已处理完，继续下一个节点
                    continue
                
                # 标准模式：检查工具调用是否正确
                is_valid_tool_call = check_tool_call(parts,is_in_retry_state)
                
                if not is_valid_tool_call:
                    tool_call_retry_count += 1
                    logger.warning(f"⚠️ [stream_agent_response] 工具调用验证失败（重试 {tool_call_retry_count}/{max_tool_call_retries}）")
                    logger.warning(f"   模型输出: {[p for p in parts if p.part_kind == 'text']}")
                    
                    if tool_call_retry_count < max_tool_call_retries:
                        # 提取模型输出的文本（包含 <notify>xxx</notify> 标记）
                        text_parts = [p.content for p in parts if p.part_kind == 'text']
                        model_text = '\n'.join(text_parts) if text_parts else '(无文本输出)'
                        
                        # 构造重试提示
                        retry_message = (
                            f"你输出了工具标记<notify></notify>但没有实际调用工具。请正确使用函数调用功能。\n"
                            f"你的输出：{model_text}\n"
                            f"请重新尝试，必须调用具体工具！而不是仅声明<notify>tool_name</notify>！"
                        )
                        
                        logger.info(f"🔄 [stream_agent_response] 注入重试提示: {retry_message[:100]}...")
                        
                        
                        
                        # 手动添加重试消息到节点
                        # 使用 RetryPromptPart 添加重试提示作为用户消息
                        
                        node=_agent_graph.ModelRequestNode(request=ModelRequest(parts=[RetryPromptPart(
                                content=retry_message,
                                timestamp=datetime.now()
                            )]))
                        
                        logger.info(f"📨 [stream_agent_response] 已添加重试消息到上下文，继续下一轮迭代")
                        is_in_retry_state = True
                        
                        # 通知前端正在重试
                        yield f"\n\n__RETRY__:{json.dumps({'reason': '工具调用格式错误', 'retry': tool_call_retry_count, 'max': max_tool_call_retries}, ensure_ascii=False)}\n\n"
                        
                        # 跳过当前节点，继续下一个迭代（模型会重新尝试）
                        continue
                    else:
                        # 超过最大重试次数，放弃并报错
                        error_msg = f"工具调用失败，已达到最大重试次数 {max_tool_call_retries}！请中止或重新生成"
                        logger.error(f"❌ [stream_agent_response] {error_msg}")
                        yield f"\n\n__ERROR__:{json.dumps({'error': error_msg}, ensure_ascii=False)}\n\n"
                        # 继续执行，让模型尝试生成文本响应
                
                # 重置重试计数器（成功调用或超过重试次数）
                if is_valid_tool_call:
                    tool_call_retry_count = 0
                    is_in_retry_state = False
                    
                    logger.info(f"🔧 [stream_agent_response] 检测到有效工具调用节点, track_tool_calls={track_tool_calls}")
                    if track_tool_calls:
                        async with node.stream(run.ctx) as handle_stream:
                            event_count = 0
                            async for event in handle_stream:
                                event_count += 1
                                logger.info(f"🔍 [stream_agent_response] 收到事件 #{event_count}, 类型: {type(event).__name__}")
                                
                                # 工具调用事件
                                if isinstance(event, FunctionToolCallEvent):
                                    logger.info(f"📞 [stream_agent_response] 立即推送工具调用开始: {event.part.tool_name}")
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
                                            logger.info(f"📝 [stream_agent_response] 已记录工具结果")
                                            break
                            
                            logger.info(f"🏁 [stream_agent_response] 工具调用节点处理完成，共 {event_count} 个事件")
                            
                            # 工具调用完成后，在后续文本前加上换行，避免紧挨在一起
                            if event_count > 0:
                                yield "\n\n"
                    else:
                        logger.warning(f"⚠️ [stream_agent_response] track_tool_calls=False，跳过工具调用追踪")
            
            # End - 结束节点
            elif Agent.is_end_node(node):
                logger.info(f"🎬 [stream_agent_response] 到达结束节点")
                # 运行完成，立即退出循环
                break
    
    # 流结束后，返回工具调用摘要（仅标准模式）
    # ReAct 模式已经通过 __TOOL_EXECUTED__ 逐个通知前端，无需再发送摘要
    if track_tool_calls and tool_calls_info and not use_react_mode:
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



from app.services.assistant_tools.pydantic_ai_tools import AssistantDeps, get_tools_schema, ASSISTANT_TOOLS

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
        parts.append(f"\nUser: {request.user_prompt}")
        
        # 3. 在用户输入后立即添加工具调用强化提示（紧邻模型输出位置）
        tool_reminder = """

---
**【⚠️ 来自系统的关键提醒】**

**项目结构基准原则**：
你必须以**当前提示词中的项目结构树**为准，忽略历史对话中的任何过时信息！
- 项目结构树会实时更新（用户可能移动、重组卡片）
- 如果用户询问卡片位置或层级关系，以**最新的树形结构**为准
- 历史对话中的结构信息可能已过时，不要依赖它
- 近期操作记录会显示最新的移动/变更信息

**卡片创作规则**：
在创建卡片或讨论卡片方案之前，必须确保已知该类型卡片的 Schema 结构！
- 如果不确定字段，先调用 get_card_type_schema 获取结构
- 不要凭想象猜测字段名，必须精确匹配 Schema

**工具调用步骤**：
如果需要执行操作（查询、创建、修改卡片等），你必须严格按以下步骤执行：
1. 先输出 `<notify>工具名</notify>` 标记（如 `<notify>create_card</notify>`）
2. 立即调用对应的函数工具！特别注意，<notify>tool_name</notify>仅仅是声明你要调用工具，并不会触发实际的工具调用，你还需要进行实际调用！
3. 等待工具返回 `{"success": true, ...}` 后再向用户确认

❌ 严禁：只描述要调用什么工具，却不实际调用函数
✅ 正确：输出 <notify> 标记 → 调用函数 → 确认结果

请立即按此流程处理用户请求。
---
"""
        parts.append(tool_reminder)
    
    final_user_prompt = "\n\n".join(parts) if parts else "（用户未输入文字，可能是想查看项目信息或需要帮助）"
    
    logger.info(f"灵感助手 system_prompt: {system_prompt}...")
    logger.info(f"灵感助手 final_user_prompt: {final_user_prompt}...")
    
    # 限额预检
    if track_stats:
        ok, reason = _precheck_quota(session, request.llm_config_id, _calc_input_tokens(system_prompt, final_user_prompt), need_calls=1)
        if not ok:
            raise ValueError(f"LLM 配额不足:{reason}")
    
    
    # 直接在创建时传入工具列表
    agent = _get_agent(
        session=session,
        llm_config_id=request.llm_config_id,
  
        system_prompt=system_prompt,
        temperature=request.temperature or 0.6,
        max_tokens=request.max_tokens or 8192,
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


async def generate_assistant_chat_streaming_react(
    session: Session,
    request: AssistantChatRequest,
    system_prompt: str,
    track_stats: bool = True
) -> AsyncGenerator[str, None]:
    """
    灵感助手 ReAct 模式流式对话生成。
    
    与标准模式的区别：
    - 不使用原生 Function Calling，而是让模型以文本格式输出工具调用
    - 系统负责解析 <tool_call> 标记并执行工具
    - 兼容更多不支持 Function Calling 的模型
    
    工具调用格式：
    ```
    <tool_call>
    {
      "name": "tool_name",
      "args": {...}
    }
    </tool_call>
    ```
    
    ⚠️ 重要注意事项：
    1. **卡片创作规则**：在创建卡片或讨论卡片方案时，LLM 必须先调用 get_card_type_schema 
       获取该类型卡片的 Schema 结构，不能凭想象猜测字段
    2. **JSON 格式**：使用 json_repair 自动修复常见错误，但仍建议提示词中强调正确格式
    3. **工具结果反馈**：工具执行结果会通过 __TOOL_EXECUTED__ 协议标记发送给前端
    4. **对话历史**：工具调用记录会被前端添加到对话历史中，供后续对话参考
    """
    from app.services.assistant_tools.pydantic_ai_tools import (
        search_cards, create_card, modify_card_field, replace_field_text,
        batch_create_cards, get_card_type_schema, get_card_content
    )
    
    # 工具映射表（手动执行）
    TOOL_FUNCTIONS = {
        "search_cards": search_cards,
        "create_card": create_card,
        "modify_card_field": modify_card_field,
        "replace_field_text": replace_field_text,
        "batch_create_cards": batch_create_cards,
        "get_card_type_schema": get_card_type_schema,
        "get_card_content": get_card_content,
    }
    
    # 获取工具 schema
    tools_schema = await get_tools_schema()
    tools_schema_text = json.dumps(tools_schema, ensure_ascii=False, indent=2)
    
    # 在系统提示中注入工具定义
    enhanced_system_prompt = system_prompt.replace("{tools_schema}", tools_schema_text)
    
    # 组装用户提示（与标准模式相同）
    parts = []
    if request.context_info:
        parts.append(request.context_info)
    
    if request.user_prompt:
        parts.append(f"\nUser: {request.user_prompt}")
        
        # React 模式的工具调用提醒
        tool_reminder = """

---
**【⚠️ ReAct 模式关键提醒】**

**0. 项目结构基准原则**：
你必须以**当前提示词中的项目结构树**为准，忽略历史对话中的任何过时信息！
- 项目结构树会实时更新（用户可能移动、重组卡片）
- 如果用户询问卡片位置或层级关系，以**最新的树形结构**为准
- 历史对话中的结构信息可能已过时，不要依赖它
- 近期操作记录会显示最新的移动/变更信息

**1. 卡片创作规则**：
在创建卡片或讨论卡片方案之前，必须确保已知该类型卡片的 Schema 结构！
- 如果不确定字段，先调用 get_card_type_schema 获取结构
- 不要凭想象猜测字段名，必须精确匹配 Schema
- 每种卡片类型的字段都不同

**2. 工具调用格式**：
<tool_call>
{
  "name": "工具名称",
  "args": { "参数名": "参数值" }
}
</tool_call>

**3. JSON 格式要求**：
- 所有字符串必须正确闭合（每个 " 都要有闭合的 "）
- 数组必须正确闭合（每个 [ 都要有闭合的 ]）
- 字符串内换行使用 \n，不要使用真实换行
- 确保所有括号、引号都成对出现

❌ 错误："description": "文本，
✅ 正确："description": "文本"
---
"""
        parts.append(tool_reminder)
    
    final_user_prompt = "\n\n".join(parts) if parts else "（用户未输入文字，可能是想查看项目信息或需要帮助）"
    
    logger.info(f"[ReAct] system_prompt 长度: {len(enhanced_system_prompt)}")
    logger.info(f"[ReAct] final_user_prompt: {final_user_prompt}...")
    
    # 限额预检
    if track_stats:
        ok, reason = _precheck_quota(session, request.llm_config_id, _calc_input_tokens(enhanced_system_prompt, final_user_prompt), need_calls=1)
        if not ok:
            raise ValueError(f"LLM 配额不足:{reason}")
    
    # 创建不带工具绑定的 Agent
    agent = _get_agent(
        session=session,
        llm_config_id=request.llm_config_id,
        system_prompt=enhanced_system_prompt,
        temperature=request.temperature or 0.6,
        max_tokens=request.max_tokens or 8192,
        timeout=request.timeout or 60,
        deps_type=AssistantDeps,
        tools=[]  # ReAct 模式不绑定工具
    )
    
    # 创建依赖上下文
    deps = AssistantDeps(session=session, project_id=request.project_id)
    
    # 使用统一的 stream_agent_response，传入 ReAct 参数
    accumulated = ""
    
    try:
        async for chunk in stream_agent_response(
            agent=agent,
            user_prompt=final_user_prompt,
            deps=deps,
            message_history=None,
            track_tool_calls=True,
            use_react_mode=True,
            react_tools_map=TOOL_FUNCTIONS
        ):
            accumulated += chunk
            yield chunk
    
    except asyncio.CancelledError:
        if track_stats:
            in_tokens = _calc_input_tokens(enhanced_system_prompt, final_user_prompt)
            out_tokens = _estimate_tokens(accumulated)
            _record_usage(session, request.llm_config_id, in_tokens, out_tokens, calls=1, aborted=True)
        return
    except Exception as e:
        logger.error(f"[ReAct] 生成失败: {e}")
        yield f"\n\n__ERROR__:{json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}"
        raise
    
    # 统计
    if track_stats:
        try:
            in_tokens = _calc_input_tokens(enhanced_system_prompt, final_user_prompt)
            out_tokens = _estimate_tokens(accumulated)
            _record_usage(session, request.llm_config_id, in_tokens, out_tokens, calls=1, aborted=False)
        except Exception as stat_e:
            logger.warning(f"[ReAct] 记录统计失败: {stat_e}")


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