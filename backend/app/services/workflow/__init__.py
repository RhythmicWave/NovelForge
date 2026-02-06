"""工作流服务模块

新一代代码式工作流系统，支持：
- 代码式 DSL 编辑
- 异步并发执行
- 节点类型系统
- 实时状态推送（SSE）
- Agent 编排

## 使用方式

### 定义节点
```python
from app.services.workflow import register_node
from app.services.workflow.nodes.base import BaseNode
from pydantic import BaseModel
from typing import AsyncIterator

class MyNodeInput(BaseModel):
    value: str

class MyNodeOutput(BaseModel):
    result: str

@register_node
class MyNode(BaseNode):
    node_type = "My.Node"
    category = "custom"
    label = "我的节点"
    description = "节点描述"
    input_model = MyNodeInput
    output_model = MyNodeOutput
    
    async def execute(self, input_data: MyNodeInput) -> AsyncIterator[MyNodeOutput]:
        # 节点处理逻辑
        yield MyNodeOutput(result=f"处理: {input_data.value}")
```

### 自动发现（在启动时调用）
```python
from app.services.workflow import discover_workflow_nodes
discover_workflow_nodes()
```
"""

from .registry import (
    get_registered_nodes,
    get_node_types,
    get_node_metadata,
    get_all_node_metadata,
    get_nodes_by_category,
    discover_workflow_nodes,
    register_node
)

from .engine import (
    WorkflowScheduler,
    StateManager,
    RunManager,
    AsyncExecutor
)

# 导入所有工作流节点模块以触发装饰器注册
from . import nodes  # noqa: F401

# 导入触发器模块以触发事件处理器注册
from . import triggers  # noqa: F401

__all__ = [
    # 注册相关
    'get_registered_nodes',
    'get_node_types',
    'get_node_metadata',
    'get_all_node_metadata',
    'get_nodes_by_category',
    'discover_workflow_nodes',
    'register_node',
    # 引擎相关
    'WorkflowScheduler',
    'StateManager',
    'RunManager',
    'AsyncExecutor',
]
