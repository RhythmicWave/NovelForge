"""工作流引擎类型定义"""

from typing import Any, Dict, List, Optional, Callable, Literal
from dataclasses import dataclass, field
from datetime import datetime


# 节点状态类型
NodeStatus = Literal["idle", "pending", "running", "success", "error", "skipped"]

# 运行状态类型
RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "paused", "timeout"]

# 端口数据类型
PortDataType = Literal[
    "string", "number", "boolean", "object", "array",
    "card", "card-list",
    "llm-response", "agent-result",
    "any"
]

# 错误处理策略
ErrorHandling = Literal["stop", "continue"]

# 日志级别
LogLevel = Literal["debug", "info", "warn", "error"]


@dataclass
class NodePort:
    """节点端口定义"""
    name: str
    type: PortDataType
    required: bool = False
    default_value: Any = None
    description: Optional[str] = None


@dataclass
class WorkflowSettings:
    """工作流执行设置"""
    max_execution_time: Optional[int] = None  # 秒
    timeout: int = 300  # 节点默认超时时间（秒）
    error_handling: ErrorHandling = "stop"
    max_concurrency: int = 5  # 最大并发节点数
    log_level: LogLevel = "info"


@dataclass
class ExecutionContext:
    """节点执行上下文"""
    run_id: int
    node_id: str
    node_type: str
    config: Dict[str, Any]
    inputs: Dict[str, Any]
    variables: Dict[str, Any]  # 全局变量
    node_outputs: Dict[str, Dict[str, Any]]  # 其他节点的输出
    settings: WorkflowSettings
    session: Any  # SQLModel Session
    
    # 辅助方法
    def get_node_output(self, node_id: str, field: Optional[str] = None) -> Any:
        """获取其他节点的输出
        
        支持两种格式：
        1. Dict[str, Any] - 旧格式，直接返回
        2. ExecutionResult - 新格式，返回 .outputs
        """
        if node_id not in self.node_outputs:
            return None
        
        node_data = self.node_outputs[node_id]
        
        # 检查是否是 ExecutionResult 对象
        if hasattr(node_data, 'outputs'):
            output = node_data.outputs
        else:
            output = node_data
        
        if field:
            return output.get(field) if isinstance(output, dict) else None
        return output
    
    def set_variable(self, name: str, value: Any) -> None:
        """设置全局变量"""
        self.variables[name] = value
    
    def get_variable(self, name: str, default: Any = None) -> Any:
        """获取全局变量"""
        return self.variables.get(name, default)


@dataclass
class ExecutionResult:
    """节点执行结果"""
    success: bool
    outputs: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    logs: List[Dict[str, Any]] = field(default_factory=list)
    should_skip_successors: bool = False  # 是否跳过后续节点
    activated_ports: Optional[List[str]] = None  # 激活的输出端口列表（用于条件分支）
    
    def add_log(self, level: str, message: str, **kwargs) -> None:
        """添加日志"""
        self.logs.append({
            "level": level,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            **kwargs
        })
    
    def get_activated_ports(self) -> List[str]:
        """获取激活的端口列表
        
        如果未显式声明，则默认激活所有输出端口
        """
        if self.activated_ports is not None:
            return self.activated_ports
        return list(self.outputs.keys())


@dataclass
class ExecutionGraph:
    """执行图"""
    nodes: Dict[str, Dict[str, Any]]  # node_id -> node_data
    edges: List[Dict[str, Any]]
    dependencies: Dict[str, List[str]]  # node_id -> [predecessor_ids]
    successors: Dict[str, List[str]]  # node_id -> [successor_ids]
    start_nodes: List[str]  # 起始节点
    topology_order: List[str]  # 拓扑排序结果
    unreachable_nodes: set = field(default_factory=set)  # 不可达节点（孤立节点）
    
    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """获取节点"""
        return self.nodes.get(node_id)
    
    def get_dependencies(self, node_id: str) -> List[str]:
        """获取节点的依赖"""
        return self.dependencies.get(node_id, [])
    
    def get_successors(self, node_id: str) -> List[str]:
        """获取节点的后继"""
        return self.successors.get(node_id, [])


@dataclass
class ExecutionEvent:
    """执行事件"""
    type: str  # run.started | node.started | node.progress | node.completed | node.error | run.completed | run.paused | run.cancelled
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_sse(self) -> str:
        """转换为SSE格式"""
        import json
        return f"event: {self.type}\ndata: {json.dumps(self.data, ensure_ascii=False)}\n\n"



