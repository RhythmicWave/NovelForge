"""多智能体辩论节点

在单个节点内实现通过两个不同配置的智能体进行多轮辩论。
支持 CoT (Chain of Thought) 思维链，Thought 内容互不可见。
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from loguru import logger
from langchain_core.messages import HumanMessage, SystemMessage

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig
from app.services.ai.core.llm_service import build_chat_model

class DebateMessage(BaseModel):
    """辩论消息结构 (强制CoT)"""
    thought: str = Field(..., description="内心的思考过程、战术分析（对方不可见）")
    content: str = Field(..., description="公开的发言内容（对方可见）")

class DebateNodeConfig(BaseNodeConfig):
    """辩论节点配置"""
    max_rounds: int = Field(3, description="最大辩论轮数 (A->B 为一轮)")
    
    # Agent A 配置
    agent_1_name: str = Field("正方", description="角色1名称")
    agent_1_system_prompt: str = Field("", description="角色1人设提示词", json_schema_extra={"x-component": "Textarea"})
    agent_1_llm_config: int = Field(..., description="角色1 LLM配置", json_schema_extra={"x-component": "LLMSelect"})
    
    # Agent B 配置
    agent_2_name: str = Field("反方", description="角色2名称")
    agent_2_system_prompt: str = Field("", description="角色2人设提示词", json_schema_extra={"x-component": "Textarea"})
    agent_2_llm_config: int = Field(..., description="角色2 LLM配置", json_schema_extra={"x-component": "LLMSelect"})
    
    temperature: float = Field(0.7, description="生成温度", ge=0.0, le=2.0)
    max_tokens: int = Field(2000, description="单次回复最大Token")

@register_node
class DebateNode(BaseNode):
    """多智能体辩论节点"""
    
    node_type = "AI.Debate"
    category = "ai"
    label = "多智能体辩论"
    description = "两个智能体针对特定主题进行多轮辩论 (支持CoT)"
    config_model = DebateNodeConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("topic", "string", description="辩论主题"),
                NodePort("context", "any", required=False, description="背景资料/上下文"),
            ],
            "outputs": [
                NodePort("summary", "string", description="辩论总结/最终发言"),
                NodePort("history", "array", description="公开对话历史 (不含思考)"),
                NodePort("full_log", "array", description="完整日志 (包含思考)"),
            ]
        }

    async def execute(
        self,
        inputs: Dict[str, Any],
        config: DebateNodeConfig
    ) -> ExecutionResult:
        """执行辩论循环"""
        session = self.context.session
        topic = inputs.get("topic", "")
        context = inputs.get("context", "")
        
        # 初始上下文组装
        user_input = f"辩论主题：{topic}"
        if context:
            user_input += f"\n\n背景资料：\n{context}"
            
        logger.info(f"[AI.Debate] 开始辩论: {config.agent_1_name} vs {config.agent_2_name}, topic={topic}")

        # 历史记录管理
        # history_public: 仅 content (用于展示和对方输入) -> List[Dict]
        # full_log: flow 记录 (用于调试) -> List[Dict]
        # agent_x_history: 包含 content + 自身 thought (作为自身上下文) -> List[BaseMessage]
        
        history_public = [] 
        full_log = []
        
        # 初始化双方的对话上下文
        # 初始消息对双方来说都是 User Message
        initial_msg = HumanMessage(content=user_input)
        
        agent_1_messages = [SystemMessage(content=config.agent_1_system_prompt), initial_msg]
        agent_2_messages = [SystemMessage(content=config.agent_2_system_prompt), initial_msg]
        
        # 辩论循环 (Round-trip)
        for round_idx in range(config.max_rounds):
            # === Agent 1 发言 ===
            msg_1 = await self._agent_turn(
                session=session,
                name=config.agent_1_name,
                llm_config_id=config.agent_1_llm_config,
                messages=agent_1_messages,
                config=config,
                round_idx=round_idx,
                role="Agent 1"
            )
            
            # 更新记录
            content_1 = msg_1.content
            thought_1 = msg_1.thought
            
            log_entry_1 = {
                "round": round_idx + 1,
                "role": config.agent_1_name,
                "type": "Agent 1",
                "thought": thought_1,
                "content": content_1
            }
            full_log.append(log_entry_1)
            history_public.append({"role": config.agent_1_name, "content": content_1})
            
            # 更新上下文
            # Agent 1 看到自己的回答 (Assistant)
            agent_1_messages.append(HumanMessage(content=f"我的思考: {thought_1}\n我的发言: {content_1}")) # 这里其实用 AssistantMessage 更合适，但 LangChain 有时对 AssistantMessage 里的 content 格式有要求。为了让模型理解这是自己的历史，可以用 text 拼接或者 Structured Output 的 history support。
            # 为了简单和稳健，还是追加为 AI Message 吧，但是带上 thought 会更好
            # 实际上，使用 model.with_structured_output 后，它是一个 tool call 或者是 json mode。
            # 下一次输入最好是把对方的 content 作为 HumanMessage 给自己。
            
            # 修正上下文策略：
            # Agent 1 已发言。
            # Appending to Agent 1: 并不需要把自己的 thought 再喂回去，除非是多步推理。
            # 简单的策略：Agent 1 讲完，把 Content 给 Agent 2。
            # Agent 2 讲完，把 Content 给 Agent 1。
            
            # Agent 2 收到 Agent 1 的 content
            agent_2_messages.append(HumanMessage(content=f"【{config.agent_1_name}】: {content_1}"))
            
            # Agent 1 自己的上下文添加？ 通常不需要添加自己的上一轮发言，除非需要上下文连贯。
            # 这里我们把自己的发言记录为 "我: ..." 追加到自己的 history 也是可以的，但更重要的是对方的回复。
            # 让我们把这一轮的对话完整的加进去：
            agent_1_messages.append(HumanMessage(content=f"【这里是历史记录无需回复】\n我已发言: {content_1}"))

            
            # === Agent 2 发言 ===
            # 现在 Agent 2 的 messages 里已经有了 Agent 1 的发言
            msg_2 = await self._agent_turn(
                session=session,
                name=config.agent_2_name,
                llm_config_id=config.agent_2_llm_config,
                messages=agent_2_messages,
                config=config,
                round_idx=round_idx,
                role="Agent 2"
            )
            
            content_2 = msg_2.content
            thought_2 = msg_2.thought
            
            log_entry_2 = {
                "round": round_idx + 1,
                "role": config.agent_2_name,
                "type": "Agent 2",
                "thought": thought_2,
                "content": content_2
            }
            full_log.append(log_entry_2)
            history_public.append({"role": config.agent_2_name, "content": content_2})
            
            # 更新上下文
            # Agent 2 收到自己的反馈记录
            agent_2_messages.append(HumanMessage(content=f"【这里是历史记录无需回复】\n我已发言: {content_2}"))
            
            # Agent 1 收到 Agent 2 的 content
            agent_1_messages.append(HumanMessage(content=f"【{config.agent_2_name}】: {content_2}"))
            
        return ExecutionResult(
            success=True,
            outputs={
                "summary": history_public[-1]["content"] if history_public else "",
                "history": history_public,
                "full_log": full_log
            }
        )

    async def _agent_turn(self, session, name, llm_config_id, messages, config, round_idx, role) -> DebateMessage:
        """执行单个 Agent 的回合"""
        try:
            model = build_chat_model(
                session=session,
                llm_config_id=llm_config_id,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                timeout=120
            )
            structured_llm = model.with_structured_output(DebateMessage)
            
            # 调用
            response = await structured_llm.ainvoke(messages)
            return response
            
        except Exception as e:
            logger.error(f"[AI.Debate] {role} ({name}) error: {e}")
            # 出错时返回默认空消息，避免崩溃
            return DebateMessage(
                thought=f"Error occurred: {str(e)}",
                content="[思考中断，无法回应]"
            )
