"""Agent 节点

提供多步骤推理和工具调用能力，支持历史对话链式传递。
"""

from typing import Any, Dict, List, Optional, AsyncIterator
from pydantic import BaseModel, Field
from loguru import logger

from ...registry import register_node
from ..base import BaseNode
from app.services.ai.core.chat_model_factory import build_chat_model
from app.services.ai.core.agent_builder import build_agent
from app.services.ai.assistant.tools import (
    ASSISTANT_TOOL_REGISTRY,
    AssistantDeps,
    set_assistant_deps,
)


# ============================================================
# Input/Output Models
# ============================================================

class AgentInput(BaseModel):
    """Agent 输入"""
    instruction: str = Field(..., description="任务指令")
    project_id: Optional[int] = Field(None, description="项目ID（使用项目相关工具时必须传递）")
    system_prompt: Optional[str] = Field(
        "你是一个专业的写作助手，帮助用户完成小说创作任务。",
        description="系统提示词"
    )
    history: List[Dict[str, Any]] = Field(default_factory=list, description="对话历史")
    llm_config_id: int = Field(..., description="LLM 配置 ID", gt=0)
    temperature: float = Field(0.7, description="温度参数", ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, description="最大生成 token 数", gt=0)
    timeout: int = Field(60, description="超时时间（秒）", gt=0)
    role_name: str = Field("助手", description="Agent 角色名称")
    tools: List[str] = Field(
        default_factory=list,
        description="启用的工具列表",
        json_schema_extra={"x-component": "ToolMultiSelect"}
    )
    max_steps: int = Field(10, ge=1, le=50, description="最大推理步数")


class AgentOutput(BaseModel):
    """Agent 输出"""
    response: str = Field(..., description="Agent 回复")
    new_history: List[Dict[str, Any]] = Field(..., description="更新后的对话历史")
    artifacts: List[Dict[str, Any]] = Field(default_factory=list, description="创建/修改的卡片列表")


# ============================================================
# Node Implementation
# ============================================================

# @register_node 还没测试好，暂时不使用
class AgentNode(BaseNode[AgentInput, AgentOutput]):
    """Agent 节点"""
    
    node_type = "AI.Agent"
    category = "ai"
    label = "AI Agent"
    description = "支持工具调用的智能体，可进行多步骤推理"
    
    input_model = AgentInput
    output_model = AgentOutput

    async def execute(self, input_data: AgentInput) -> AsyncIterator[AgentOutput]:
        """执行 Agent"""
        
        # 使用显式传递的项目ID（可选）
        project_id = input_data.project_id or -1
        
        # 设置 AssistantDeps
        deps = AssistantDeps(
            session=self.context.session,
            project_id=project_id
        )
        set_assistant_deps(deps)
        
        # 构建 ChatModel
        model = build_chat_model(
            session=self.context.session,
            llm_config_id=input_data.llm_config_id,
            temperature=input_data.temperature,
            max_tokens=input_data.max_tokens,
            timeout=input_data.timeout,
        )
        
        # 筛选工具
        selected_tools = []
        for tool_name in input_data.tools:
            tool = ASSISTANT_TOOL_REGISTRY.get(tool_name)
            if tool:
                selected_tools.append(tool)
            else:
                logger.warning(f"[AI.Agent] 未找到工具: {tool_name}")
        
        if not selected_tools:
            logger.warning("[AI.Agent] 未选择任何工具，将使用纯文本模式")
        
        # 构建 Agent
        agent = build_agent(
            model=model,
            tools=selected_tools,
            system_prompt=input_data.system_prompt,
            enable_summarization=False,
        )
        
        # 构建消息
        messages = []
        
        # 添加历史消息
        if input_data.history:
            messages.extend(input_data.history)
        
        # 添加当前指令
        messages.append({
            "role": "user",
            "content": input_data.instruction
        })
        
        # 执行 Agent（非流式）
        result = await agent.ainvoke({"messages": messages})
        
        # 提取响应
        response_text = ""
        final_messages = []
        
        if isinstance(result, dict):
            result_messages = result.get("messages", [])
            if result_messages:
                # 获取最后一条 AI 消息
                for msg in reversed(result_messages):
                    if hasattr(msg, 'content'):
                        response_text = msg.content
                        break
                    elif isinstance(msg, dict) and msg.get("role") == "assistant":
                        response_text = msg.get("content", "")
                        break
                
                # 保存完整历史
                final_messages = result_messages
        
        # 转换消息格式为可序列化的字典
        serializable_history = []
        for msg in final_messages:
            if hasattr(msg, 'dict'):
                serializable_history.append(msg.dict())
            elif hasattr(msg, 'model_dump'):
                serializable_history.append(msg.model_dump())
            elif isinstance(msg, dict):
                serializable_history.append(msg)
            else:
                serializable_history.append({
                    "role": "assistant" if hasattr(msg, 'content') else "user",
                    "content": str(msg)
                })
        
        logger.info(
            f"[AI.Agent] Agent 执行成功: role={input_data.role_name}, "
            f"tools={len(selected_tools)}, response_length={len(response_text)}"
        )
        
        yield AgentOutput(
            response=response_text,
            new_history=serializable_history,
            artifacts=[]  # TODO: 跟踪工具调用创建的卡片
        )

