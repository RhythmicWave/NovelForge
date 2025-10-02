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