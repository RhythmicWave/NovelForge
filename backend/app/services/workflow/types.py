"""工作流引擎类型定义

只包含新代码式工作流系统使用的类型。
"""

from typing import Literal, Any, Callable, Dict
from dataclasses import dataclass, field
from datetime import datetime


# 节点状态类型
NodeStatus = Literal["idle", "pending", "running", "success", "error", "skipped"]

# 运行状态类型
RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "paused", "timeout"]

# 错误处理策略
ErrorHandling = Literal["stop", "continue"]

# 日志级别
LogLevel = Literal["debug", "info", "warn", "error"]


@dataclass
class NodeMetadata:
    """节点元数据"""
    type: str
    category: str
    label: str
    description: str
    documentation: str  # 完整的文档（从 docstring 提取）
    input_schema: Dict[str, Any]  # 从 input_model 生成的 JSON Schema
    output_schema: Dict[str, Any]  # 从 output_model 生成的 JSON Schema
    executor: Callable  # 节点执行器类


@dataclass
class WorkflowSettings:
    """工作流执行设置"""
    max_execution_time: int | None = None  # 秒
    timeout: int = 300  # 节点默认超时时间（秒）
    error_handling: ErrorHandling = "stop"
    max_concurrency: int = 5  # 最大并发节点数
    log_level: LogLevel = "info"


@dataclass
class ExecutionContext:
    """节点执行上下文（简化版，用于兼容旧节点）"""
    run_id: int
    node_id: str
    node_type: str
    config: dict[str, Any]
    inputs: dict[str, Any]
    variables: dict[str, Any]  # 全局变量
    node_outputs: dict[str, dict[str, Any]]  # 其他节点的输出
    settings: WorkflowSettings
    session: Any  # SQLModel Session
    checkpoint: dict[str, Any] | None = None  # 检查点数据（恢复时注入）
    """检查点数据（恢复时由执行器注入）
    
    节点可以通过 self.context.checkpoint 访问上次保存的检查点数据。
    
    示例：
        checkpoint = getattr(self.context, 'checkpoint', None)
        if checkpoint:
            start_index = checkpoint.get('processed_count', 0)
        else:
            start_index = 0
    
    注意：
    - 只保存轻量级元数据（索引、计数器、ID等）
    - 不保存业务数据（卡片内容、处理结果等）
    - 大小限制：< 10KB
    """


@dataclass
class ExecutionEvent:
    """执行事件（用于 SSE 推送）"""
    type: str  # run.started | node.started | node.progress | node.completed | node.error | run.completed | run.paused | run.cancelled
    data: dict
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_sse(self) -> str:
        """转换为SSE格式"""
        import json
        return f"event: {self.type}\ndata: {json.dumps(self.data, ensure_ascii=False)}\n\n"

