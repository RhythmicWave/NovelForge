"""核心模块

包含事件系统、启动初始化、配置管理等核心功能。
"""

# 事件系统
from .events import Event, on_event, emit_event, get_event_handlers, discover_event_handlers

# 启动系统
from .startup import startup, shutdown

# 配置系统
from .config import settings

__all__ = [
    # 事件系统
    'Event',
    'on_event',
    'emit_event',
    'get_event_handlers',
    'discover_event_handlers',
    # 启动系统
    'startup',
    'shutdown',
    # 配置系统
    'settings',
]
