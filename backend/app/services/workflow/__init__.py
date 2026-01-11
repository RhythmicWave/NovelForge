"""工作流服务模块

工作流节点注册、执行和管理。

## 使用方式

节点通过 @register_node 装饰器自动注册，启动时通过 discover_workflow_nodes() 自动发现。

### 定义节点
```python
from app.services.workflow import register_node

@register_node("MyNode.Type")
def my_node_handler(session, state, params):
    # 节点处理逻辑
    return result
```

### 自动发现（在启动时调用）
```python
from app.services.workflow import discover_workflow_nodes
discover_workflow_nodes()
```
"""

from .registry import register_node, get_registered_nodes, get_node_types, discover_workflow_nodes

# 导入所有工作流节点模块以触发装饰器注册
from . import nodes_impl  # noqa: F401

__all__ = [
    'register_node',
    'get_registered_nodes',
    'get_node_types',
    'discover_workflow_nodes',
]
