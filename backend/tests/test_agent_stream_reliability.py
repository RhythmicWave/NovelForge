import asyncio
import json
import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.ai.core import chat_model_factory
from app.services.ai.core.react_text_agent import stream_chat_with_react_protocol
from app.services.ai.core.tool_agent_stream import stream_agent_with_tools
from app.utils.stream_utils import wrap_sse_stream


def _decode_frame(frame: str) -> dict:
    envelope = json.loads(frame.split("data: ", 1)[1])
    return json.loads(envelope["content"])


def test_sse_done_is_emitted_only_after_normal_completion():
    async def source():
        yield json.dumps({"type": "token", "data": {"text": "ok"}})

    async def collect():
        return [item async for item in wrap_sse_stream(source(), emit_done=True)]

    events = [_decode_frame(item) for item in asyncio.run(collect())]
    assert [event["type"] for event in events] == ["token", "done"]


def test_sse_exception_does_not_emit_done():
    async def source():
        yield json.dumps({"type": "token", "data": {"text": "partial"}})
        raise RuntimeError("upstream disconnected")

    async def collect():
        frames = []
        with pytest.raises(RuntimeError, match="upstream disconnected"):
            async for item in wrap_sse_stream(source(), emit_done=True):
                frames.append(item)
        return frames

    events = [_decode_frame(item) for item in asyncio.run(collect())]
    assert [event["type"] for event in events] == ["token"]


def test_sse_cancellation_does_not_emit_done():
    async def source():
        await asyncio.Event().wait()
        yield json.dumps({"type": "token", "data": {"text": "never"}})

    async def consume(frames):
        async for item in wrap_sse_stream(source(), emit_done=True):
            frames.append(item)

    async def run():
        frames = []
        task = asyncio.create_task(consume(frames))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return frames

    assert asyncio.run(run()) == []


def test_google_provider_receives_max_retries(monkeypatch):
    captured = {}

    class FakeGoogleModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(chat_model_factory, "ChatGoogleGenerativeAI", FakeGoogleModel)
    monkeypatch.setattr(
        chat_model_factory.llm_config_service,
        "resolve_transport_settings",
        lambda **_: {
            "provider": "google",
            "use_responses_api": False,
            "request_base": None,
            "default_headers": {},
            "api_protocol": "auto",
        },
    )

    chat_model_factory.build_chat_model_from_payload(
        provider="google",
        model_name="gemini-test",
        api_key="test-key",
        temperature=0.2,
        max_tokens=256,
        timeout=90,
        max_retries=2,
    )

    assert captured["max_retries"] == 2
    assert captured["max_output_tokens"] == 256
    assert captured["timeout"] == 90.0


def test_shared_agent_retry_budget_is_call_site_parameter():
    assert inspect.signature(stream_agent_with_tools).parameters["max_retries"].default is None
    assert inspect.signature(stream_chat_with_react_protocol).parameters["max_retries"].default is None
