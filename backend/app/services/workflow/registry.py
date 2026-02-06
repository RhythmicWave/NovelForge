"""工作流节点注册机制

使用装饰器自动注册工作流节点，支持 Pydantic 模型和元数据。
"""

from typing import Dict, Callable, List, Optional
from loguru import logger
import inspect

from .types import NodeMetadata


# 节点注册表
_NODE_REGISTRY: Dict[str, NodeMetadata] = {}


def register_node(cls):
    """类装饰器：注册类式工作流节点
    
    直接调用节点类的 get_metadata() 方法获取 NodeMetadata 对象。
    """
    if not inspect.isclass(cls):
        raise TypeError("@register_node must be used on a class")

    # 检查必需的属性
    node_type = getattr(cls, "node_type", None)
    if not node_type:
        raise ValueError(f"Node class {cls.__name__} must define 'node_type'")

    # 直接调用节点的 get_metadata() 方法，返回 NodeMetadata 对象
    metadata = cls.get_metadata()
    
    _NODE_REGISTRY[node_type] = metadata
    logger.debug(f"[节点注册] {node_type} ({metadata.category}) -> {cls.__name__}")
    return cls


def get_registered_nodes() -> Dict[str, Callable]:
    """获取所有已注册的节点执行器
    
    Returns:
        节点类型到执行类的映射
    """
    return {type_name: meta.executor for type_name, meta in _NODE_REGISTRY.items()}


def get_node_metadata(node_type: str) -> Optional[NodeMetadata]:
    """获取节点元数据
    
    Args:
        node_type: 节点类型
        
    Returns:
        节点元数据，不存在则返回None
    """
    return _NODE_REGISTRY.get(node_type)


def get_all_node_metadata() -> List[NodeMetadata]:
    """获取所有节点元数据
    
    Returns:
        节点元数据列表
    """
    return list(_NODE_REGISTRY.values())


def get_node_types() -> List[str]:
    """获取所有已注册的节点类型名称
    
    Returns:
        节点类型名称列表
    """
    return list(_NODE_REGISTRY.keys())


def get_nodes_by_category(category: str) -> List[NodeMetadata]:
    """按分类获取节点
    
    Args:
        category: 分类名称
        
    Returns:
        该分类下的所有节点元数据
    """
    return [meta for meta in _NODE_REGISTRY.values() if meta.category == category]


class NodeRegistry:
    """节点注册表包装类
    
    提供节点类型检查和获取接口
    """

    def has_node(self, node_type: str) -> bool:
        """检查节点类型是否存在"""
        return node_type in _NODE_REGISTRY

    def get(self, node_type: str) -> Optional[Callable]:
        """获取节点执行器"""
        meta = _NODE_REGISTRY.get(node_type)
        return meta.executor if meta else None
    
    def list_nodes(self) -> List[str]:
        """列出所有已注册的节点类型"""
        return list(_NODE_REGISTRY.keys())


def discover_workflow_nodes():
    """记录已注册的工作流节点数量

    所有工作流节点模块已在 app.services.workflow.__init__.py 中导入，
    装饰器在包导入时自动执行注册。
    """
    logger.info(f"[节点发现] 已加载 {len(_NODE_REGISTRY)} 个工作流节点")

    # 按分类统计
    categories = {}
    for meta in _NODE_REGISTRY.values():
        categories[meta.category] = categories.get(meta.category, 0) + 1

    for cat, count in categories.items():
        logger.debug(f"  - {cat}: {count} 个节点")
