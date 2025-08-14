from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

class ContinuationRequest(BaseModel):
    previous_content: str
    llm_config_id: int
    stream: bool = False
    # 新增可选上下文字段（向后兼容）
    project_id: Optional[int] = None
    volume_number: Optional[int] = None
    chapter_number: Optional[int] = None
    participants: Optional[List[str]] = None
    # 采样与超时（可选）
    temperature: Optional[float] = Field(default=None, description="采样温度 0-2，留空使用模型默认")
    max_tokens: Optional[int] = Field(default=None, description="生成的最大token数，留空使用默认")
    timeout: Optional[float] = Field(default=None, description="生成超时(秒)，留空使用默认")
    # 新增：上下文抽屉模板作为草稿尾部
    current_draft_tail: Optional[str] = Field(default=None, description="上下文模板，将在装配阶段作为草稿尾部注入")
    # 新增：参数卡选择的提示词名称（优先使用该提示词作为系统提示词）
    prompt_name: Optional[str] = Field(default=None, description="参数卡选择的提示词名称")

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

    class Config:
        extra = 'ignore'