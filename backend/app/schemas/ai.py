from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

class ContinuationRequest(BaseModel):
    previous_content: str = Field(default="", description="已写的章节内容")
    llm_config_id: int
    stream: bool = False
    # 可选上下文字段（向后兼容）
    project_id: Optional[int] = None
    volume_number: Optional[int] = None
    chapter_number: Optional[int] = None
    participants: Optional[List[str]] = None
    # 采样与超时（可选）
    temperature: Optional[float] = Field(default=None, description="采样温度 0-2，留空使用模型默认")
    max_tokens: Optional[int] = Field(default=None, description="生成的最大token数，留空使用默认")
    timeout: Optional[float] = Field(default=None, description="生成超时(秒)，留空使用默认")
    # 上下文信息（引用上下文 + 事实子图）
    context_info: Optional[str] = Field(default=None, description="上下文信息，包括引用内容和事实子图")
    # 已有内容字数统计（用于指导续写长度）
    existing_word_count: Optional[int] = Field(default=None, description="已有章节正文的字数统计")
    # 参数卡选择的提示词名称（优先使用该提示词作为系统提示词）
    prompt_name: Optional[str] = Field(default=None, description="参数卡选择的提示词名称")
    # 是否追加"直接输出连续的小说正文"尾缀（默认 True 兼容原有续写）
    append_continuous_novel_directive: bool = Field(default=True, description="是否追加连续小说正文指令")

class ContinuationResponse(BaseModel):
    content: str


class AssistantChatRequest(BaseModel):
    """灵感助手对话请求（新格式）"""
    # 新格式：前端发送统一的上下文信息和用户输入
    context_info: str = Field(description="完整的项目上下文信息（包含项目结构、操作历史、引用卡片等）")
    user_prompt: str = Field(default="", description="用户当前输入（可为空）")
    
    # 必需字段
    project_id: int = Field(description="项目ID（用于工具调用作用域）")
    llm_config_id: int = Field(description="LLM配置ID")
    prompt_name: str = Field(default="灵感对话", description="系统提示词名称")
    
    # 可选参数
    temperature: Optional[float] = Field(default=None, description="采样温度 0-2")
    max_tokens: Optional[int] = Field(default=None, description="最大token数")
    timeout: Optional[float] = Field(default=None, description="超时秒数")
    stream: bool = Field(default=True, description="是否流式输出")
    thinking_enabled: Optional[bool] = Field(default=None, description="是否启用推理/Thinking 输出（仅部分模型支持）")
    # 上下文摘要配置（仅灵感助手使用，前端可选传入）
    context_summarization_enabled: Optional[bool] = Field(default=None, description="是否启用上下文摘要中间件（对过长对话做摘要压缩）")
    context_summarization_threshold: Optional[int] = Field(default=None, description="触发上下文摘要的 token 阈值")
    react_mode_enabled: Optional[bool] = Field(default=None, description="是否启用 React 文本协议工具调用模式")


class GeneralAIRequest(BaseModel):
    input: Dict[str, Any]
    llm_config_id: Optional[int] = None
    prompt_name: Optional[str] = None
    response_model_name: Optional[Dict[str, Any]] | Optional[str] = None
    response_model_schema: Optional[Dict[str, Any]] = None  # 用于动态创建模型
    # 采样与超时（可选）
    temperature: Optional[float] = Field(default=None, description="采样温度 0-2，留空使用模型默认")
    max_tokens: Optional[int] = Field(default=None, description="生成的最大token数，留空使用默认")
    timeout: Optional[float] = Field(default=None, description="生成超时(秒)，留空使用默认")
    # 前端直接传入的依赖（JSON 字符串，例如 {\"all_entity_names\":[...]}")
    deps: Optional[str] = Field(default=None, description="依赖注入数据(JSON字符串)，例如实体名称列表等")

    class Config:
        extra = 'ignore'