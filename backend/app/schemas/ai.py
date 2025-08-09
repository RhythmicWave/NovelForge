from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class ContinuationRequest(BaseModel):
    previous_content: str
    llm_config_id: int
    stream: bool = False

class ContinuationResponse(BaseModel):
    content: str


class GeneralAIRequest(BaseModel):
    input: Dict[str, Any]
    llm_config_id: Optional[int] = None
    prompt_name: Optional[str] = None
    response_model_name: Optional[str] = None
    response_model_schema: Optional[Dict[str, Any]] = None  # 用于动态创建模型

    class Config:
        extra = 'ignore'