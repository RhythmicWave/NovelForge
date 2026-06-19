from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.schemas.llm_config import LLMCapabilityRecommendedMode, LLMCapabilityTestRequest
from app.services import llm_config_service
from app.services.ai.core.chat_model_factory import build_chat_model_from_payload
from app.services.ai.core.react_text_agent import build_react_user_prompt, parse_react_action_payload


DEFAULT_USER_AGENT = "NovelForge/1.0"
REPAIR_USER_AGENT_CANDIDATES = ("NovelForge/1.0", "Mozilla/5.0", "CherryStudio/1.0")
TEST_NAMES = (
    "models_list",
    "basic_chat",
    "review",
    "stream",
    "structured",
    "native_tools",
    "react_tools",
)


class CapabilityStructuredProbe(BaseModel):
    ok: bool = Field(description="Whether the probe succeeded.")
    text: str = Field(description="Short result text.")


@tool
def get_test_value() -> dict:
    """Return a fixed harmless value for capability testing."""
    return {"success": True, "value": "ok"}


@dataclass
class ProbeResult:
    status: str
    message: str
    error_type: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"status": self.status, "message": self.message}
        if self.error_type:
            data["error_type"] = self.error_type
        return data


def _empty_results() -> dict[str, ProbeResult]:
    return {name: ProbeResult(status="skip", message="Not tested") for name in TEST_NAMES}


def _sanitize_message(text: str, api_key: str | None = None) -> str:
    cleaned = str(text or "")
    if api_key:
        cleaned = cleaned.replace(api_key, "***")
    return cleaned[:1200]


def classify_llm_error(exc: Exception | str) -> str:
    text = str(exc or "").lower()
    if "401" in text or "invalid api key" in text or "unauthorized" in text or "authentication" in text:
        return "auth_error"
    if "429" in text or "rate limit" in text or "ratelimit" in text or "quota" in text:
        return "rate_limited"
    gateway_markers = (
        "your request was blocked",
        "cloudflare",
        "error 1020",
        " waf",
        "waf ",
        "blocked",
        "policy blocked",
        "access denied",
        " 444",
    )
    if any(marker in text for marker in gateway_markers) or ("403" in text and "block" in text):
        return "gateway_blocked"
    if "400" in text or "invalid_request" in text or "unsupported parameter" in text or "bad request" in text:
        return "bad_request"
    tool_markers = (
        "tool_choice",
        "tool calls",
        "tool_calls",
        "bind_tools",
        "function calling",
        "tools unsupported",
        "does not support tools",
    )
    if any(marker in text for marker in tool_markers):
        return "tools_unsupported"
    stream_markers = ("stream", "sse", "chunk", "event stream")
    if any(marker in text for marker in stream_markers):
        return "stream_unsupported"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    return "unknown"


def _result_from_exception(exc: Exception, api_key: str | None = None) -> ProbeResult:
    return ProbeResult(
        status="fail",
        message=_sanitize_message(str(exc), api_key),
        error_type=classify_llm_error(exc),
    )


def _message_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "".join(parts).strip()
    if content is None:
        return ""
    return str(content).strip()


def _payload_kwargs(request: LLMCapabilityTestRequest, *, user_agent: str | None = None, api_protocol: str | None = None) -> dict[str, Any]:
    return {
        "provider": request.provider,
        "model_name": request.model_name,
        "api_key": request.api_key,
        "api_base": request.api_base,
        "api_protocol": api_protocol or request.api_protocol,
        "custom_request_path": request.custom_request_path,
        "user_agent": user_agent if user_agent is not None else request.user_agent,
        "temperature": 0,
        "max_tokens": 64,
        "timeout": 20,
    }


async def _probe_models_list(request: LLMCapabilityTestRequest, *, user_agent: str | None = None) -> ProbeResult:
    if not request.test_models_list:
        return ProbeResult(status="skip", message="Model list test was not requested")

    provider = (request.provider or "").lower()
    try:
        if provider in {"openai", "openai_compatible"}:
            transport = llm_config_service.resolve_transport_settings(
                provider=provider,
                api_base=request.api_base,
                api_protocol=request.api_protocol,
                models_path=request.models_path,
                user_agent=user_agent if user_agent is not None else request.user_agent,
            )
            if not transport["models_url"]:
                return ProbeResult(status="skip", message="Missing api_base for model list")
            headers = {
                "Authorization": f"Bearer {request.api_key}",
                "Content-Type": "application/json",
                **transport["default_headers"],
            }
            async with httpx.AsyncClient() as client:
                response = await client.get(transport["models_url"], headers=headers, timeout=10.0)
                response.raise_for_status()
                data = response.json()
            count = len(data.get("data") or []) if isinstance(data, dict) else 0
            return ProbeResult(status="pass", message=f"Model list returned {count} item(s)")

        if provider == "google":
            if not request.api_key:
                return ProbeResult(status="skip", message="Missing api_key for Google model list")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={request.api_key}",
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()
            count = len(data.get("models") or []) if isinstance(data, dict) else 0
            return ProbeResult(status="pass", message=f"Model list returned {count} item(s)")

        return ProbeResult(status="skip", message="Provider model list probe is not implemented")
    except Exception as exc:
        return _result_from_exception(exc, request.api_key)


async def _probe_basic_chat(request: LLMCapabilityTestRequest, *, user_agent: str | None = None, api_protocol: str | None = None) -> ProbeResult:
    try:
        model = build_chat_model_from_payload(**_payload_kwargs(request, user_agent=user_agent, api_protocol=api_protocol))
        response = await model.ainvoke([HumanMessage(content="ping")])
        if not _message_text(response):
            raise ValueError("Empty response")
        return ProbeResult(status="pass", message="Basic chat returned a non-empty response")
    except Exception as exc:
        return _result_from_exception(exc, request.api_key)


async def _probe_review(request: LLMCapabilityTestRequest, *, user_agent: str | None = None, api_protocol: str | None = None) -> ProbeResult:
    try:
        model = build_chat_model_from_payload(**_payload_kwargs(request, user_agent=user_agent, api_protocol=api_protocol))
        response = await model.ainvoke(
            [
                SystemMessage(content="Reply with one short Chinese review sentence."),
                HumanMessage(content="这是一段测试文本。"),
            ]
        )
        if not _message_text(response):
            raise ValueError("Empty response")
        return ProbeResult(status="pass", message="Review-style chat returned a non-empty response")
    except Exception as exc:
        return _result_from_exception(exc, request.api_key)


async def _probe_stream(request: LLMCapabilityTestRequest, *, user_agent: str | None = None, api_protocol: str | None = None) -> ProbeResult:
    try:
        model = build_chat_model_from_payload(**_payload_kwargs(request, user_agent=user_agent, api_protocol=api_protocol))
        async for chunk in model.astream([HumanMessage(content="ping")]):
            if _message_text(chunk):
                return ProbeResult(status="pass", message="Stream returned at least one token")
        raise ValueError("Stream returned no token")
    except Exception as exc:
        result = _result_from_exception(exc, request.api_key)
        if result.error_type == "unknown":
            result.error_type = "stream_unsupported"
        return result


async def _probe_structured(request: LLMCapabilityTestRequest, *, user_agent: str | None = None, api_protocol: str | None = None) -> ProbeResult:
    try:
        model = build_chat_model_from_payload(**_payload_kwargs(request, user_agent=user_agent, api_protocol=api_protocol))
        structured = model.with_structured_output(CapabilityStructuredProbe)
        response = await structured.ainvoke([HumanMessage(content='Return JSON with ok=true and text="ok".')])
        if response is None:
            raise ValueError("Empty structured response")
        return ProbeResult(status="pass", message="Structured output returned a valid object")
    except Exception as exc:
        return _result_from_exception(exc, request.api_key)


async def _probe_native_tools(request: LLMCapabilityTestRequest, *, user_agent: str | None = None, api_protocol: str | None = None) -> ProbeResult:
    try:
        model = build_chat_model_from_payload(**_payload_kwargs(request, user_agent=user_agent, api_protocol=api_protocol))
        bound_model = model.bind_tools([get_test_value])
        response = await bound_model.ainvoke(
            [
                SystemMessage(content="You must call the provided tool exactly once."),
                HumanMessage(content="Call get_test_value now."),
            ]
        )
        tool_calls = getattr(response, "tool_calls", None) or []
        for call in tool_calls:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name == "get_test_value":
                result = get_test_value.invoke({})
                if isinstance(result, dict) and result.get("success") is True:
                    return ProbeResult(status="pass", message="Native tool call completed")
        raise ValueError("Model did not produce the dummy tool call")
    except Exception as exc:
        result = _result_from_exception(exc, request.api_key)
        if result.error_type == "unknown":
            result.error_type = "tools_unsupported"
        return result


async def _probe_react_tools(request: LLMCapabilityTestRequest, *, user_agent: str | None = None, api_protocol: str | None = None) -> ProbeResult:
    try:
        model = build_chat_model_from_payload(**_payload_kwargs(request, user_agent=user_agent, api_protocol=api_protocol))
        tool_descriptions = {
            "get_test_value": {
                "description": "Return a fixed harmless test value.",
                "args": {},
            }
        }
        user_prompt = build_react_user_prompt(
            context_info="",
            user_prompt="Call get_test_value once. Use only the Action JSON block.",
            tool_descriptions=tool_descriptions,
            protocol_instructions=(
                'Use this exact tool-call format: <Action>{"tool":"get_test_value","args":{}}</Action>. '
                "Call the tool now."
            ),
        )
        response = await model.ainvoke([SystemMessage(content="You are a tool protocol tester."), HumanMessage(content=user_prompt)])
        parsed = parse_react_action_payload(_message_text(response))
        if parsed:
            tool_name, _args = parsed
            if tool_name == "get_test_value":
                result = get_test_value.invoke({})
                if isinstance(result, dict) and result.get("success") is True:
                    return ProbeResult(status="pass", message="ReAct tool protocol completed")
        raise ValueError("Model did not emit a valid ReAct Action block")
    except Exception as exc:
        result = _result_from_exception(exc, request.api_key)
        if result.error_type == "unknown":
            result.error_type = "tools_unsupported"
        return result


def _make_tags(results: dict[str, ProbeResult], recommended: LLMCapabilityRecommendedMode) -> list[str]:
    tags: list[str] = []
    if results["basic_chat"].status == "pass":
        tags.append("基础聊天可用")
    if results["review"].status == "pass":
        tags.append("审核可用")
    if results["stream"].status == "pass":
        tags.append("流式可用")
    elif results["stream"].status == "fail":
        tags.append("流式失败：建议关闭")
    if results["structured"].status == "pass":
        tags.append("结构化输出可用")
    elif results["structured"].status == "fail":
        tags.append("结构化输出失败")
    if results["native_tools"].status == "pass":
        tags.append("原生工具可用")
    elif results["native_tools"].status == "fail":
        tags.append("原生工具失败")
    if results["react_tools"].status == "pass":
        tags.append("ReAct可用")
    if any(item.error_type == "gateway_blocked" for item in results.values()):
        tags.append("疑似网关/WAF拦截")
    if results["basic_chat"].status == "pass" and results["review"].status == "pass" and recommended["assistant_mode"] == "plain":
        tags.append("建议仅普通写作/审核")
    return tags


def _overall(results: dict[str, ProbeResult], recommended: LLMCapabilityRecommendedMode) -> str:
    if results["basic_chat"].status != "pass":
        return "unusable"
    if results["native_tools"].status == "pass" and results["review"].status == "pass":
        return "full"
    if recommended["assistant_mode"] == "react" and results["react_tools"].status == "pass":
        return "react_assistant"
    if results["review"].status == "pass":
        return "writing_review_only"
    return "plain_only"


def _summary(overall: str, results: dict[str, ProbeResult], recommended: LLMCapabilityRecommendedMode) -> str:
    if overall == "unusable":
        if results["models_list"].status == "pass" and results["basic_chat"].status == "fail":
            return "模型列表可用，但聊天请求被拦截。可尝试兼容修复。"
        return "基础连接失败，当前配置不可用。"
    if overall == "full":
        return "基础聊天、审核和原生工具调用可用。"
    if overall == "react_assistant":
        return "原生工具不可用，但 ReAct 工具模式可用，建议灵感助手使用 ReAct。"
    if overall == "writing_review_only":
        return "模型适合普通写作和审核，不建议使用标准工具助手。"
    if recommended.get("disable_stream"):
        return "基础聊天可用，但流式输出失败，建议关闭流式。"
    return "模型仅通过基础聊天检测。"


async def run_capability_test(request: LLMCapabilityTestRequest) -> dict[str, Any]:
    results = _empty_results()
    raw_errors: dict[str, str] = {}
    repair_notes: list[str] = []
    recommended: LLMCapabilityRecommendedMode = {
        "api_protocol": request.api_protocol,
        "assistant_mode": "standard",
        "disable_stream": False,
        "use_default_user_agent": False,
        "recommended_user_agent": None,
    }
    effective_user_agent = request.user_agent
    effective_api_protocol = request.api_protocol

    results["models_list"] = await _probe_models_list(request)
    results["basic_chat"] = await _probe_basic_chat(request)

    if request.try_repair and results["basic_chat"].status == "fail":
        repair_notes.append(f"User-Agent=当前配置 基础连接失败：{results['basic_chat'].message}")
        seen_user_agents = {(request.user_agent or "").strip()}
        for candidate in REPAIR_USER_AGENT_CANDIDATES:
            if candidate in seen_user_agents:
                continue
            seen_user_agents.add(candidate)
            ua_basic = await _probe_basic_chat(request, user_agent=candidate)
            if ua_basic.status == "pass":
                repair_notes.append(f"User-Agent={candidate} 修复成功")
                recommended["use_default_user_agent"] = True
                recommended["recommended_user_agent"] = candidate
                effective_user_agent = candidate
                results["basic_chat"] = ua_basic
                results["models_list"] = await _probe_models_list(request, user_agent=candidate)
                break
            repair_notes.append(f"User-Agent={candidate} 基础连接失败：{ua_basic.message}")

    if request.try_repair and results["basic_chat"].status == "fail":
        alternate_protocol = "responses" if request.api_protocol == "chat_completions" else "chat_completions"
        alternate = await _probe_basic_chat(request, user_agent=effective_user_agent, api_protocol=alternate_protocol)
        if alternate.status == "pass":
            repair_notes.append(f"Basic chat passed after switching protocol to {alternate_protocol}")
            recommended["api_protocol"] = alternate_protocol
            effective_api_protocol = alternate_protocol
            results["basic_chat"] = alternate

    if results["basic_chat"].status == "pass":
        results["review"] = await _probe_review(request, user_agent=effective_user_agent, api_protocol=effective_api_protocol)
        results["stream"] = await _probe_stream(request, user_agent=effective_user_agent, api_protocol=effective_api_protocol)
        if results["stream"].status == "fail":
            recommended["disable_stream"] = True
            if request.try_repair:
                repair_notes.append("Stream failed while basic chat passed; recommend disabling stream")
        results["structured"] = await _probe_structured(request, user_agent=effective_user_agent, api_protocol=effective_api_protocol)
        results["native_tools"] = await _probe_native_tools(request, user_agent=effective_user_agent, api_protocol=effective_api_protocol)
        if results["native_tools"].status == "pass":
            recommended["assistant_mode"] = "standard"
        else:
            results["react_tools"] = await _probe_react_tools(request, user_agent=effective_user_agent, api_protocol=effective_api_protocol)
            if results["react_tools"].status == "pass":
                recommended["assistant_mode"] = "react"
                if request.try_repair:
                    repair_notes.append("Native tools failed but ReAct passed; recommend ReAct assistant mode")
            else:
                recommended["assistant_mode"] = "plain" if results["review"].status == "pass" else "standard"
    else:
        recommended["assistant_mode"] = "standard"

    for name, result in results.items():
        if result.status == "fail":
            raw_errors[name] = result.message

    tests = {name: result.to_dict() for name, result in results.items()}
    overall = _overall(results, recommended)
    tags = _make_tags(results, recommended)
    if repair_notes:
        tags.extend([f"修复尝试：{note}" for note in repair_notes])

    return {
        "overall": overall,
        "recommended_mode": recommended,
        "tests": tests,
        "tags": tags,
        "summary": _summary(overall, results, recommended),
        "raw_errors": raw_errors,
        "repair_notes": repair_notes,
    }
