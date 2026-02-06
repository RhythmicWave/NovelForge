"""Agent 节点

提供多步骤推理和工具调用能力，支持历史对话链式传递。
"""

from typing import Any, Dict, List, Optional
from pydantic import Field
from loguru import logger
import json

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode
from .base import BaseAINodeConfig
from app.services.ai.core.llm_service import build_chat_model
from app.services.ai.core.agent_builder import build_agent
from app.services.ai.assistant.tools import (
    ASSISTANT_TOOLS,
    ASSISTANT_TOOL_REGISTRY,
    AssistantDeps,
    set_assistant_deps,
)


class AgentConfig(BaseAINodeConfig):
    """Agent 配置"""
    
    role_name: str = Field(
        "助手",
        description="Agent 角色名称"
    )
    tools: List[str] = Field(
        default_factory=list,
        description="启用的工具列表",
        json_schema_extra={"x-component": "ToolMultiSelect"}
    )
    max_steps: int = Field(
        10,
        ge=1,
        le=50,
        description="最大推理步数"
    )


@register_node
class AgentNode(BaseNode):
    """Agent 节点"""
    
    node_type = "AI.Agent"
    category = "ai"
    label = "AI Agent"
    description = "支持工具调用的智能体，可进行多步骤推理"
    config_model = AgentConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("system_prompt", "string", required=False, description="系统提示词"),
                NodePort("instruction", "string", description="任务指令"),
                NodePort("history", "array", required=False, description="对话历史"),
            ],
            "outputs": [
                NodePort("response", "string", description="Agent 回复"),
                NodePort("new_history", "array", description="更新后的对话历史"),
                NodePort("artifacts", "array", description="创建/修改的卡片列表"),
            ]
        }

    async def execute(
        self,
        inputs: Dict[str, Any],
        config: AgentConfig
    ) -> ExecutionResult:
        """执行 Agent"""
        
        system_prompt = inputs.get("system_prompt", "你是一个专业的写作助手，帮助用户完成小说创作任务。")
        instruction = inputs.get("instruction", "")
        history = inputs.get("history", [])
        
        if not instruction:
            return ExecutionResult(
                success=False,
                error="缺少任务指令"
            )
        
        try:
            # 获取项目 ID
            project_id = self.context.variables.get("project_id")
            if not project_id:
                trigger = self.context.variables.get("trigger", {})
                project_id = trigger.get("project_id")
            
            # 设置 AssistantDeps
            deps = AssistantDeps(
                session=self.context.session,
                project_id=project_id or -1
            )
            set_assistant_deps(deps)
            
            # 构建 ChatModel
            model = build_chat_model(
                session=self.context.session,
                llm_config_id=config.llm_config_id,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                timeout=config.timeout,
            )
            
            # 筛选工具
            selected_tools = []
            for tool_name in config.tools:
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
                system_prompt=system_prompt,
                enable_summarization=False,
            )
            
            # 构建消息
            messages = []
            
            # 添加历史消息
            if history and isinstance(history, list):
                messages.extend(history)
            
            # 添加当前指令
            messages.append({
                "role": "user",
                "content": instruction
            })
            
            # 执行 Agent（非流式）
            response_text = ""
            final_messages = []
            
            # 使用 agent.invoke 进行非流式调用
            result = await agent.ainvoke({"messages": messages})
            
            # 提取响应
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
                f"[AI.Agent] Agent 执行成功: role={config.role_name}, "
                f"tools={len(selected_tools)}, response_length={len(response_text)}"
            )
            
            return ExecutionResult(
                success=True,
                outputs={
                    "response": response_text,
                    "new_history": serializable_history,
                    "artifacts": [],  # TODO: 跟踪工具调用创建的卡片
                }
            )
            
        except Exception as e:
            logger.error(f"[AI.Agent] Agent 执行失败: {e}")
            return ExecutionResult(
                success=False,
                error=f"Agent 执行失败: {str(e)}"
            )
