"""工作流节点注册机制

使用装饰器自动注册工作流节点，支持类型定义和元数据。
"""

from typing import Dict, Callable, List, Optional, Any
from dataclasses import dataclass
from loguru import logger

from .types import NodePort, PortDataType
import inspect
from typing import Type, Union
from pydantic import BaseModel


@dataclass
class NodeMetadata:
    """节点元数据"""
    type: str
    category: str
    label: str
    description: str
    inputs: List[NodePort]
    outputs: List[NodePort]
    config_schema: Dict[str, Any]
    executor: Callable


# 节点注册表
_NODE_REGISTRY: Dict[str, NodeMetadata] = {}





def register_node(cls):
    """类装饰器：注册类式工作流节点 (v2.0)
    
    自动从类属性读取元数据：
    - node_type
    - category
    - label
    - description (可选)
    - config_model (Pydantic Model) -> 生成 config_schema
    - get_ports() -> inputs/outputs
    """
    # Local import to avoid circular dependency at module level if nodes import registry
    # But ideally registry is independent. We'll duck-type or assume structure.
    
    if not inspect.isclass(cls):
        raise TypeError("@register_node must be used on a class")

    # Extract metadata from class attributes
    node_type = getattr(cls, "node_type", None)
    category = getattr(cls, "category", "custom")
    label = getattr(cls, "label", node_type)
    description = getattr(cls, "description", "")
    
    if not node_type:
        raise ValueError(f"Node class {cls.__name__} must define 'node_type'")

    # Configuration Schema
    config_model = getattr(cls, "config_model", None)
    config_schema = {}
    if config_model and issubclass(config_model, BaseModel):
        config_schema = config_model.model_json_schema()
    
    # Ports
    inputs = []
    outputs = []
    if hasattr(cls, "get_ports"):
        ports = cls.get_ports()
        inputs = ports.get("inputs", [])
        outputs = ports.get("outputs", [])

    metadata = NodeMetadata(
        type=node_type,
        category=category,
        label=label,
        description=description,
        inputs=inputs,
        outputs=outputs,
        config_schema=config_schema,
        executor=cls  # The class itself is the executor factory
    )
    
    _NODE_REGISTRY[node_type] = metadata
    logger.debug(f"[节点注册(Class)] {node_type} ({category}) -> {cls.__name__}")
    return cls


def get_registered_nodes() -> Dict[str, Callable]:
    """获取所有已注册的节点执行器
    
    Returns:
        节点类型到执行函数的映射
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
