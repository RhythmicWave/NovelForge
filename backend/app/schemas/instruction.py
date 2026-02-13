"""指令流生成相关的数据模型

定义了指令格式、生成请求和响应等数据结构。
"""

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


# ==================== 指令格式定义 ====================

class InstructionBase(BaseModel):
    """指令基类"""
    op: str = Field(..., description="指令操作类型")


class SetInstruction(InstructionBase):
    """设置字段值指令"""
    op: Literal["set"] = "set"
    path: str = Field(..., description="JSON Pointer 格式的字段路径，如 /name 或 /config/theme")
    value: Any = Field(..., description="要设置的值，可以是任意类型")


class AppendInstruction(InstructionBase):
    """向数组追加元素指令"""
    op: Literal["append"] = "append"
    path: str = Field(..., description="JSON Pointer 格式的数组路径")
    value: Any = Field(..., description="要追加的元素")


class DoneInstruction(InstructionBase):
    """生成完成标志指令"""
    op: Literal["done"] = "done"


# 联合类型：所有指令类型
Instruction = SetInstruction | AppendInstruction | DoneInstruction


# ==================== 生成配置 ====================

class GenerationConfig(BaseModel):
    """卡片生成配置
    
    定义了如何生成卡片内容的策略和提示。
    """
    mode: Literal["instruction_stream"] = Field(
        default="instruction_stream",
        description="生成模式，当前仅支持指令流模式"
    )
    prompt_template: Optional[str] = Field(
        default=None,
        description="全局提示词模板（可选）"
    )
    field_hints: Optional[Dict[str, str]] = Field(
        default=None,
        description="字段级生成提示，键为字段路径，值为提示文本"
    )
    field_order: Optional[List[str]] = Field(
        default=None,
        description="建议的字段生成顺序"
    )
    custom: Optional[Dict[str, Any]] = Field(
        default=None,
        description="自定义配置（扩展用）"
    )


# ==================== API 请求/响应模型 ====================

class ConversationMessage(BaseModel):
    """对话消息"""
    role: Literal["system", "user", "assistant"] = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容")


class InstructionGenerateRequest(BaseModel):
    """指令流生成请求"""
    
    # LLM 配置
    llm_config_id: int = Field(..., description="LLM 配置 ID")
    
    # 用户输入
    user_prompt: str = Field(default="", description="用户输入的提示词或回复")
    
    # Schema 定义
    response_model_schema: Dict[str, Any] = Field(..., description="目标数据结构的 JSON Schema")
    
    # 当前数据状态
    current_data: Dict[str, Any] = Field(default_factory=dict, description="当前已生成的数据")
    
    # 对话上下文
    conversation_context: List[ConversationMessage] = Field(
        default_factory=list,
        description="对话历史（前端维护）"
    )
    
    # 生成配置（可选）
    generation_config: Optional[GenerationConfig] = Field(
        default=None,
        description="生成配置，如果为空则使用默认配置"
    )
    
    # 提示词模板（可选，覆盖默认）
    prompt_template: Optional[str] = Field(
        default=None,
        description="自定义提示词模板"
    )
    
    # 上下文信息（可选）
    context_info: Optional[str] = Field(
        default=None,
        description="上下文注入信息（如相关实体、已有卡片等）"
    )
    
    # 采样参数
    temperature: Optional[float] = Field(default=0.7, description="采样温度")
    max_tokens: Optional[int] = Field(default=None, description="最大生成 token 数")
    timeout: Optional[float] = Field(default=150, description="超时时间（秒）")
    
    # 依赖数据（如实体名列表）
    deps: Optional[str] = Field(default=None, description="依赖数据，用于校验")


# ==================== SSE 事件类型 ====================

class ThinkingEvent(BaseModel):
    """思考事件（AI 的自然语言输出）"""
    type: Literal["thinking"] = "thinking"
    text: str = Field(..., description="思考内容或提问")


class InstructionEvent(BaseModel):
    """指令事件（已校验的指令）"""
    type: Literal["instruction"] = "instruction"
    instruction: Instruction = Field(..., description="指令对象")


class WarningEvent(BaseModel):
    """警告事件（非致命错误）"""
    type: Literal["warning"] = "warning"
    text: str = Field(..., description="警告信息")


class ErrorEvent(BaseModel):
    """错误事件（致命错误）"""
    type: Literal["error"] = "error"
    text: str = Field(..., description="错误信息")


class DoneEvent(BaseModel):
    """完成事件"""
    type: Literal["done"] = "done"
    success: bool = Field(default=True, description="是否成功完成")
    message: Optional[str] = Field(default=None, description="完成消息")


# 联合类型：所有事件类型
StreamEvent = ThinkingEvent | InstructionEvent | WarningEvent | ErrorEvent | DoneEvent
