"""核心模块

包含事件系统、启动初始化、配置管理等核心功能。
"""

# 事件系统
from .events import Event, on_event, emit_event, get_event_handlers, discover_event_handlers

# 配置系统
from .config import settings

# 注意：startup 和 shutdown 不在此导出，避免循环导入
# 使用时请直接从 app.core.startup 导入

__all__ = [
    # 事件系统
    'Event',
    'on_event',
    'emit_event',
    'get_event_handlers',
    'discover_event_handlers',
    # 配置系统
    'settings',
]
