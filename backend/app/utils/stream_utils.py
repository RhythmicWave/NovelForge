"""流式响应工具函数"""

import json
from typing import AsyncGenerator


async def wrap_sse_stream(generator: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
    """将纯文本流包装为 SSE (Server-Sent Events) 格式
    
    Args:
        generator: 异步文本生成器
        
    Yields:
        SSE 格式的数据流
    """
    async for item in generator:
        yield f"data: {json.dumps({'content': item}, ensure_ascii=False)}\n\n"
