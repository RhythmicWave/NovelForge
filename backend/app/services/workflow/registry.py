"""工作流节点注册机制

使用装饰器自动注册工作流节点，支持自动发现。
"""

from typing import Dict, Callable, List
from loguru import logger


_NODE_REGISTRY: Dict[str, Callable] = {}


def register_node(node_type: str):
    """装饰器：自动注册工作流节点
    
    用法:
        @register_node("Card.Read")
        def node_card_read(session, state, params):
            ...
    
    Args:
        node_type: 节点类型名称
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable):
        _NODE_REGISTRY[node_type] = func
        logger.debug(f"[节点注册] {node_type} -> {func.__name__}")
        return func
    return decorator


def get_registered_nodes() -> Dict[str, Callable]:
    """获取所有已注册的节点
    
    Returns:
        节点类型到处理函数的映射
    """
    return _NODE_REGISTRY.copy()


def get_node_types() -> List[str]:
    """获取所有已注册的节点类型名称
    
    Returns:
        节点类型名称列表
    """
    return list(_NODE_REGISTRY.keys())


def discover_workflow_nodes():
    """记录已注册的工作流节点数量
    
    所有工作流节点模块已在 app.services.workflow.__init__.py 中导入，
    装饰器在包导入时自动执行注册。
    """
    logger.debug(f"[节点发现] 已加载 {len(_NODE_REGISTRY)} 个工作流节点")
