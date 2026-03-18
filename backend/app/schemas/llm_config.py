
from sqlmodel import SQLModel
from typing import Literal, Optional


LLMApiProtocol = Literal["chat_completions", "responses"]

class LLMConfigBase(SQLModel):
    provider: str
    display_name: Optional[str] = None
    model_name: str
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    api_protocol: LLMApiProtocol = "chat_completions"
    custom_request_path: Optional[str] = None
    models_path: Optional[str] = None
    user_agent: Optional[str] = None
    # 配额（-1 表示不限）与统计（只读场景外部可见）
    token_limit: Optional[int] = -1
    call_limit: Optional[int] = -1
    rpm_limit: Optional[int] = -1
    tpm_limit: Optional[int] = -1
    used_tokens_input: Optional[int] = 0
    used_tokens_output: Optional[int] = 0
    used_calls: Optional[int] = 0

class LLMConfigCreate(LLMConfigBase):
    pass

class LLMConfigRead(LLMConfigBase):
    id: int

class LLMConfigUpdate(SQLModel):
    provider: Optional[str] = None
    display_name: Optional[str] = None
    model_name: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    api_protocol: Optional[LLMApiProtocol] = None
    custom_request_path: Optional[str] = None
    models_path: Optional[str] = None
    user_agent: Optional[str] = None
    token_limit: Optional[int] = None
    call_limit: Optional[int] = None
    rpm_limit: Optional[int] = None
    tpm_limit: Optional[int] = None
    used_tokens_input: Optional[int] = None
    used_tokens_output: Optional[int] = None
    used_calls: Optional[int] = None

class LLMConnectionTest(SQLModel):
    provider: str
    model_name: str
    api_base: Optional[str] = None
    api_key: str
    api_protocol: LLMApiProtocol = "chat_completions"
    custom_request_path: Optional[str] = None
    user_agent: Optional[str] = None

class LLMGetModelsRequest(SQLModel):
    provider: str
    api_base: Optional[str] = None
    api_key: str
    api_protocol: LLMApiProtocol = "chat_completions"
    models_path: Optional[str] = None
    user_agent: Optional[str] = None
