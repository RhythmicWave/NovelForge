
from datetime import datetime
from typing import Any, Literal, Optional

from sqlmodel import SQLModel


LLMApiProtocol = Literal["chat_completions", "responses"]
LLMAssistantMode = Literal["auto", "standard", "react", "plain"]
LLMCapabilityOverall = Literal["full", "writing_review_only", "react_assistant", "plain_only", "unusable", "unknown"]
LLMCapabilityStatus = Literal["pass", "fail", "skip"]

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
    capability_summary: Optional[dict[str, Any]] = None
    recommended_assistant_mode: LLMAssistantMode = "auto"
    disable_stream: bool = False
    capability_last_checked_at: Optional[datetime] = None

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
    capability_summary: Optional[dict[str, Any]] = None
    recommended_assistant_mode: Optional[LLMAssistantMode] = None
    disable_stream: Optional[bool] = None
    capability_last_checked_at: Optional[datetime] = None

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


class LLMCapabilityTestRequest(LLMConnectionTest):
    models_path: Optional[str] = None
    test_models_list: bool = False
    try_repair: bool = False
    save_result: bool = False
    config_id: Optional[int] = None


class LLMCapabilityProbeResult(SQLModel):
    status: LLMCapabilityStatus
    message: str
    error_type: Optional[str] = None


class LLMCapabilityRecommendedMode(SQLModel):
    api_protocol: LLMApiProtocol
    assistant_mode: Literal["standard", "react", "plain"]
    disable_stream: bool = False
    use_default_user_agent: bool = False
    recommended_user_agent: Optional[str] = None


class LLMCapabilityTests(SQLModel):
    models_list: LLMCapabilityProbeResult
    basic_chat: LLMCapabilityProbeResult
    review: LLMCapabilityProbeResult
    stream: LLMCapabilityProbeResult
    structured: LLMCapabilityProbeResult
    native_tools: LLMCapabilityProbeResult
    react_tools: LLMCapabilityProbeResult


class LLMCapabilityTestResult(SQLModel):
    overall: LLMCapabilityOverall
    recommended_mode: LLMCapabilityRecommendedMode
    tests: LLMCapabilityTests
    tags: list[str]
    summary: str
    raw_errors: dict[str, str] = {}
    repair_notes: list[str] = []
