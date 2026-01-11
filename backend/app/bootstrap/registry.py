"""初始化器注册机制

提供装饰器和自动发现功能，实现插件化的初始化系统。

使用方式：
    @initializer(name="prompts", order=10)
    def init_prompts(session: Session):
        ...
        
    # 自动发现并执行所有初始化器
    discover_and_run_initializers(session)
"""

from typing import Callable, List, Tuple
from sqlmodel import Session
from loguru import logger


# 全局注册表：存储所有初始化器
_INITIALIZERS: List[Tuple[int, str, Callable]] = []


def initializer(name: str, order: int = 100):
    """初始化器装饰器
    
    将函数注册为初始化器，支持自动发现和按顺序执行。
    
    Args:
        name: 初始化器名称，用于日志输出
        order: 执行顺序，数字越小越先执行（默认100）
        
    Example:
        @initializer(name="prompts", order=10)
        def init_prompts(session: Session):
            logger.info("初始化提示词...")
    """
    def decorator(func: Callable):
        # 注册到全局列表
        _INITIALIZERS.append((order, name, func))
        logger.debug(f"[初始化器注册] {name} (order={order}) -> {func.__name__}")
        return func
    return decorator


def get_registered_initializers() -> List[Tuple[int, str, Callable]]:
    """获取所有已注册的初始化器
    
    Returns:
        按order排序的初始化器列表 [(order, name, func), ...]
    """
    return sorted(_INITIALIZERS, key=lambda x: x[0])


def discover_initializers():
    """记录已注册的初始化器数量
    
    所有初始化器模块已在 app.bootstrap.__init__.py 中导入，
    装饰器在包导入时自动执行注册。
    """
    logger.debug(f"[初始化器发现] 已加载 {len(_INITIALIZERS)} 个初始化器")


def run_initializers(session: Session):
    """执行所有已注册的初始化器
    
    按 order 顺序依次执行初始化器。
    
    Args:
        session: 数据库会话
    """
    initializers = get_registered_initializers()
    
    if not initializers:
        logger.warning("[初始化器] 未发现任何已注册的初始化器")
        return
    
    logger.info(f"[初始化器] 发现 {len(initializers)} 个初始化器，开始执行...")
    
    for order, name, func in initializers:
        try:
            logger.info(f"[初始化器] 执行: {name} (order={order})")
            func(session)
        except Exception as e:
            logger.error(f"[初始化器] 执行失败 {name}: {e}")
            raise


def discover_and_run_initializers(session: Session):
    """自动发现并执行所有初始化器
    
    这是主入口函数，完成：
    1. 自动发现所有初始化器模块
    2. 按顺序执行所有初始化器
    
    Args:
        session: 数据库会话
    """
    discover_initializers()
    run_initializers(session)
