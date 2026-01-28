"""工作流服务模块

新一代工作流系统，支持：
- 可视化编辑（Vue Flow）
- DAG执行引擎
- 节点类型系统
- 实时状态推送（SSE）
- Agent编排

## 使用方式

### 定义节点
```python
from app.services.workflow import register_workflow_node
from app.services.workflow.engine.types import ExecutionContext, ExecutionResult, NodePort

@register_workflow_node(
    type="MyNode.Type",
    category="custom",
    label="我的节点",
    description="节点描述",
    inputs=[NodePort("input", "any")],
    outputs=[NodePort("output", "any")]
)
def execute_my_node(context: ExecutionContext) -> ExecutionResult:
    # 节点处理逻辑
    return ExecutionResult(success=True, outputs={"output": result})
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
    discover_workflow_nodes
)

from .engine import (
    WorkflowScheduler,
    GraphBuilder,
    WorkflowExecutor,
    StateManager,
    RunManager
)

# 导入所有工作流节点模块以触发装饰器注册
from . import nodes  # noqa: F401

__all__ = [
    # 注册相关
    'get_registered_nodes',
    'get_node_types',
    'get_node_metadata',
    'get_all_node_metadata',
    'get_nodes_by_category',
    'discover_workflow_nodes',
    # 引擎相关
    'WorkflowScheduler',
    'GraphBuilder',
    'WorkflowExecutor',
    'StateManager',
    'RunManager',
]
