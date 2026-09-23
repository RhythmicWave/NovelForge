"""流式响应工具函数。"""

import asyncio
import json
from typing import AsyncGenerator


def _encode_content(content: str) -> str:
    return f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"


def _event_type(item: str) -> str | None:
    if not isinstance(item, str):
        return None
    try:
        parsed = json.loads(item)
    except (TypeError, ValueError):
        return None
    return parsed.get("type") if isinstance(parsed, dict) else None


def _encode_protocol_event(event: dict) -> str:
    return _encode_content(json.dumps(event, ensure_ascii=False))


async def wrap_sse_stream(
    generator: AsyncGenerator[str, None],
    *,
    emit_done: bool = False,
) -> AsyncGenerator[str, None]:
    """将 Agent 事件包装成 SSE，并在正常结束时发送明确的 ``done``。

    这里不主动生成心跳；客户端用独立的协议空闲阈值判断断联。异常和取消
    继续向外传播，因此不会错误地产生 ``done``。
    """
    last_type: str | None = None
    try:
        async for item in generator:
            last_type = _event_type(item)
            yield _encode_content(item)
    except asyncio.CancelledError:
        raise
    else:
        if emit_done and last_type not in {"error", "cancelled"}:
            yield _encode_protocol_event({"type": "done", "data": {}})
