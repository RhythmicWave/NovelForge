from typing import Optional, Any, List
from pydantic import BaseModel


class WorkflowBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: Optional[bool] = True
    is_built_in: Optional[bool] = False
    version: Optional[int] = 1
    dsl_version: Optional[int] = 1
    definition_json: Optional[dict] = None
    keep_run_history: Optional[bool] = False  # Default to False (Transient)


class WorkflowCreate(WorkflowBase):
    pass


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    version: Optional[int] = None
    dsl_version: Optional[int] = None
    definition_json: Optional[dict] = None
    keep_run_history: Optional[bool] = None


class WorkflowRead(WorkflowBase):
    id: int

    class Config:
        from_attributes = True


class WorkflowRunRead(BaseModel):
    id: int
    workflow_id: int
    definition_version: int
    status: str
    scope_json: Optional[dict] = None
    params_json: Optional[dict] = None
    idempotency_key: Optional[str] = None
    summary_json: Optional[dict] = None
    error_json: Optional[dict] = None
    workflow: Optional["WorkflowRead"] = None  # Include basic info

    class Config:
        from_attributes = True


class RunRequest(BaseModel):
    scope_json: Optional[dict] = None
    params_json: Optional[dict] = None
    idempotency_key: Optional[str] = None


class CancelResponse(BaseModel):
    ok: bool
    message: Optional[str] = None


class NodeExecutionStatus(BaseModel):
    """节点执行状态"""
    node_id: str
    node_type: str
    status: str  # idle | pending | running | success | error | skipped
    progress: int
    error: Optional[str] = None


class RunStatus(BaseModel):
    """工作流运行状态（包含节点状态）"""
    run_id: int
    workflow_id: int
    status: str  # idle | pending | running | succeeded | failed | cancelled
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[dict] = None
    nodes: List[NodeExecutionStatus]


# ---- Node Types ----

class NodePortInfo(BaseModel):
    """节点端口信息"""
    name: str
    type: str
    required: Optional[bool] = None
    description: Optional[str] = None


class NodeTypeInfo(BaseModel):
    """节点类型信息"""
    type: str
    category: str
    label: str
    description: str
    inputs: List[NodePortInfo]
    outputs: List[NodePortInfo]
    config_schema: Optional[dict] = None


class NodeTypesResponse(BaseModel):
    """节点类型列表响应"""
    node_types: List[NodeTypeInfo]

