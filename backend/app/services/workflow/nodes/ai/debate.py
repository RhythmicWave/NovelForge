"""多智能体辩论节点

在单个节点内实现通过两个不同配置的智能体进行多轮辩论。
支持 CoT (Chain of Thought) 思维链，Thought 内容互不可见。
支持进度报告和断点续传。
"""

from typing import Any, Dict, List, Optional, AsyncIterator, TYPE_CHECKING
from pydantic import BaseModel, Field
from loguru import logger

if TYPE_CHECKING:
    from ...engine.async_executor import ProgressEvent

from ...registry import register_node
from ..base import BaseNode
from app.services.ai.core.llm_service import generate_structured


# ============================================================
# Helper Models
# ============================================================

class DebateMessage(BaseModel):
    """辩论消息结构 (强制CoT)"""
    thought: str = Field(..., description="内心的思考过程、战术分析（对方不可见）")
    content: str = Field(..., description="公开的发言内容（对方可见）")


# ============================================================
# Input/Output Models
# ============================================================

class DebateInput(BaseModel):
    """辩论节点输入"""
    topic: str = Field(..., description="辩论主题")
    context: Optional[str] = Field(None, description="背景资料/上下文")
    max_rounds: int = Field(3, description="最大辩论轮数 (A->B 为一轮)", ge=1, le=20)
    
    # Agent 1 配置
    agent_1_name: str = Field("正方", description="角色1名称")
    agent_1_system_prompt: str = Field("", description="角色1人设提示词", json_schema_extra={"x-component": "Textarea"})
    agent_1_llm_config: int = Field(..., description="角色1 LLM配置", json_schema_extra={"x-component": "LLMSelect"})
    
    # Agent 2 配置
    agent_2_name: str = Field("反方", description="角色2名称")
    agent_2_system_prompt: str = Field("", description="角色2人设提示词", json_schema_extra={"x-component": "Textarea"})
    agent_2_llm_config: int = Field(..., description="角色2 LLM配置", json_schema_extra={"x-component": "LLMSelect"})
    
    temperature: float = Field(0.7, description="生成温度", ge=0.0, le=2.0)
    max_tokens: int = Field(2000, description="单次回复最大Token")


class DebateOutput(BaseModel):
    """辩论节点输出"""
    summary: str = Field(..., description="辩论总结/最终发言")
    history: List[Dict[str, Any]] = Field(..., description="公开对话历史 (不含思考)，格式为[{'role': '正方'/'反方', 'content': '发言内容'}, ...]，如需展示，建议进行格式处理")
    full_log: List[Dict[str, Any]] = Field(..., description="完整日志 (包含思考)")
    total_rounds: int = Field(..., description="实际完成的辩论轮数")


# ============================================================
# Node Implementation
# ============================================================

@register_node
class DebateNode(BaseNode[DebateInput, DebateOutput]):
    """多智能体辩论节点"""
    
    node_type = "AI.Debate"
    category = "ai"
    label = "多智能体辩论"
    description = "两个智能体针对特定主题进行多轮辩论 (支持CoT、进度报告、断点续传)"
    
    input_model = DebateInput
    output_model = DebateOutput

    async def execute(self, input_data: DebateInput) -> AsyncIterator:
        """执行辩论循环（串行处理，支持断点续传）"""
        from ...engine.async_executor import ProgressEvent
        
        # 1. 检查点恢复
        checkpoint = getattr(self.context, 'checkpoint', None)
        completed_rounds = checkpoint.get('completed_rounds', 0) if checkpoint else 0
        history_public = checkpoint.get('history_public', []) if checkpoint else []
        full_log = checkpoint.get('full_log', []) if checkpoint else []
        
        # 恢复对话上下文（简化：只保存消息内容）
        agent_1_context = checkpoint.get('agent_1_context', []) if checkpoint else []
        agent_2_context = checkpoint.get('agent_2_context', []) if checkpoint else []
        
        # 初始化（仅首次）
        if completed_rounds == 0:
            user_input = f"辩论主题：{input_data.topic}"
            if input_data.context:
                user_input += f"\n\n背景资料：\n{input_data.context}"
                
            logger.info(f"[AI.Debate] 开始辩论: {input_data.agent_1_name} vs {input_data.agent_2_name}, topic={input_data.topic}")

            # 初始化上下文（只保存字符串）
            agent_1_context = [user_input]
            agent_2_context = [user_input]
        else:
            logger.info(f"[AI.Debate] 从检查点恢复: 已完成 {completed_rounds}/{input_data.max_rounds} 轮")
        
        # 2. 辩论循环（串行处理）
        for round_idx in range(completed_rounds, input_data.max_rounds):
            try:
                # === Agent 1 发言 ===
                logger.info(f"[AI.Debate] 第 {round_idx + 1} 轮 - {input_data.agent_1_name} 发言中...")
                
                msg_1 = await self._agent_turn(
                    name=input_data.agent_1_name,
                    llm_config_id=input_data.agent_1_llm_config,
                    system_prompt=input_data.agent_1_system_prompt,
                    context=agent_1_context,
                    input_data=input_data,
                    role="Agent 1"
                )
                
                # 更新记录
                content_1 = msg_1.content
                thought_1 = msg_1.thought
                
                log_entry_1 = {
                    "round": round_idx + 1,
                    "role": input_data.agent_1_name,
                    "type": "Agent 1",
                    "thought": thought_1,
                    "content": content_1
                }
                full_log.append(log_entry_1)
                history_public.append({"role": input_data.agent_1_name, "content": content_1})
                
                # 更新上下文（简化：只保存内容字符串）
                agent_2_context.append(f"【{input_data.agent_1_name}】: {content_1}")
                agent_1_context.append(f"【我的发言】: {content_1}")
                
                # === Agent 2 发言 ===
                logger.info(f"[AI.Debate] 第 {round_idx + 1} 轮 - {input_data.agent_2_name} 发言中...")
                
                msg_2 = await self._agent_turn(
                    name=input_data.agent_2_name,
                    llm_config_id=input_data.agent_2_llm_config,
                    system_prompt=input_data.agent_2_system_prompt,
                    context=agent_2_context,
                    input_data=input_data,
                    role="Agent 2"
                )
                
                content_2 = msg_2.content
                thought_2 = msg_2.thought
                
                log_entry_2 = {
                    "round": round_idx + 1,
                    "role": input_data.agent_2_name,
                    "type": "Agent 2",
                    "thought": thought_2,
                    "content": content_2
                }
                full_log.append(log_entry_2)
                history_public.append({"role": input_data.agent_2_name, "content": content_2})
                
                # 更新上下文
                agent_2_context.append(f"【我的发言】: {content_2}")
                agent_1_context.append(f"【{input_data.agent_2_name}】: {content_2}")
                
                # 3. 报告进度（一轮辩论完成）
                completed_rounds = round_idx + 1
                progress_percent = (completed_rounds / input_data.max_rounds) * 100
                
                logger.info(f"[AI.Debate] 推送进度: {progress_percent:.1f}% ({completed_rounds}/{input_data.max_rounds})")
                
                yield ProgressEvent(
                    percent=progress_percent,
                    message=f"第 {completed_rounds}/{input_data.max_rounds} 轮辩论完成",
                    data={
                        'completed_rounds': completed_rounds,
                        'history_public': history_public,
                        'full_log': full_log,
                        'agent_1_context': agent_1_context,
                        'agent_2_context': agent_2_context
                    }
                )
                
            except Exception as e:
                logger.error(f"[AI.Debate] 第 {round_idx + 1} 轮出错: {e}", exc_info=True)
                # 出错时停止辩论，返回当前结果
                break
        
        # 4. 返回最终结果
        logger.info(f"[AI.Debate] 辩论完成，共 {completed_rounds} 轮")
        
        yield DebateOutput(
            summary=history_public[-1]["content"] if history_public else "辩论未完成",
            history=history_public,
            full_log=full_log,
            total_rounds=completed_rounds
        )

    async def _agent_turn(
        self,
        name: str,
        llm_config_id: int,
        system_prompt: str,
        context: List[str],
        input_data: DebateInput,
        role: str
    ) -> DebateMessage:
        """执行单个 Agent 的回合（使用 generate_structured）"""
        try:
            # 构建 user_prompt（将上下文合并）
            user_prompt = "\n\n".join(context)
            
            # 使用 generate_structured 函数（包含配额管理、重试、token 统计）
            response = await generate_structured(
                session=self.context.session,
                llm_config_id=llm_config_id,
                user_prompt=user_prompt,
                output_type=DebateMessage,
                system_prompt=system_prompt,
                temperature=input_data.temperature,
                max_tokens=input_data.max_tokens,
                max_retries=3
            )
            
            logger.info(f"[AI.Debate] {role} ({name}) 发言完成")
            return response
            
        except Exception as e:
            logger.error(f"[AI.Debate] {role} ({name}) 调用失败: {e}", exc_info=True)
            # 出错时抛出异常，让外层处理
            raise

