"""AI服务模块

统一的LLM调用、结构化生成、续写和助手服务。
"""

from .llm_service import (
    build_chat_model,
    generate_structured,
    generate_continuation_streaming,
)
from .assistant_service import (
    generate_assistant_chat_streaming,
)

__all__ = [
    'build_chat_model',
    'generate_structured',
    'generate_continuation_streaming',
    'generate_assistant_chat_streaming',
]
