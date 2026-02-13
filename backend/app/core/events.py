"""事件总线系统

统一的事件发布-订阅机制，支持装饰器注册和自动发现。
"""

from typing import Callable, Dict, List, Any, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class Event:
    """事件基类
    
    Attributes:
        name: 事件名称
        data: 事件数据
        source: 事件源
    """
    name: str
    data: Dict[str, Any]
    source: Optional[str] = None


# 事件处理器注册表
_EVENT_HANDLERS: Dict[str, List[Callable]] = {}


def on_event(event_name: str):
    """装饰器：注册事件处理器
    
    用法:
        @on_event("card.saved")
        def handle_card_saved(event: Event):
            ...
    
    Args:
        event_name: 事件名称
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable):
        if event_name not in _EVENT_HANDLERS:
            _EVENT_HANDLERS[event_name] = []
        _EVENT_HANDLERS[event_name].append(func)
        logger.debug(f"[事件注册] {event_name} -> {func.__name__}")
        return func
    return decorator


def emit_event(event_name: str, data: Dict[str, Any], source: Optional[str] = None) -> None:
    """发布事件
    
    Args:
        event_name: 事件名称
        data: 事件数据
        source: 事件源
    """
    event = Event(name=event_name, data=data, source=source)
    handlers = _EVENT_HANDLERS.get(event_name, [])
    
    if not handlers:
        logger.debug(f"[事件发布] {event_name} - 无处理器")
        return
    
    logger.info(f"[事件发布] {event_name} - {len(handlers)}个处理器")
    
    for handler in handlers:
        try:
            handler(event)
        except Exception as e:
            logger.error(f"[事件处理失败] {event_name} - {handler.__name__}: {e}")


def get_event_handlers(event_name: str) -> List[Callable]:
    """获取指定事件的所有处理器
    
    Args:
        event_name: 事件名称
        
    Returns:
        处理器列表
    """
    return _EVENT_HANDLERS.get(event_name, []).copy()


def get_all_events() -> List[str]:
    """获取所有已注册的事件名称
    
    Returns:
        事件名称列表
    """
    return list(_EVENT_HANDLERS.keys())


def discover_event_handlers():
    """记录已注册的事件处理器数量
    
    所有事件处理器模块已在 app.services.__init__.py 中导入，
    装饰器在包导入时自动执行注册。
    """
    total_handlers = sum(len(handlers) for handlers in _EVENT_HANDLERS.values())
    logger.debug(f"[事件发现] 已加载 {len(_EVENT_HANDLERS)} 个事件，共 {total_handlers} 个处理器")


def clear_handlers(event_name: Optional[str] = None) -> None:
    """清除事件处理器（主要用于测试）
    
    Args:
        event_name: 事件名称，如果为None则清除所有
    """
    if event_name is None:
        _EVENT_HANDLERS.clear()
        logger.debug("[事件系统] 清除所有处理器")
    else:
        _EVENT_HANDLERS.pop(event_name, None)
        logger.debug(f"[事件系统] 清除 {event_name} 的处理器")
