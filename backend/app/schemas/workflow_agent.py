from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkflowAgentMode(str, Enum):
    SUGGEST = "suggest"
    AUTO_APPLY = "auto_apply"


class WorkflowAgentChatRequest(BaseModel):
    workflow_id: int = Field(description="当前编辑工作流 ID")
    llm_config_id: int = Field(description="用于对话的 LLM 配置 ID")
    user_prompt: str = Field(default="", description="用户输入")
    mode: WorkflowAgentMode = Field(default=WorkflowAgentMode.SUGGEST, description="工作模式")
    conversation_id: Optional[str] = Field(default=None, description="会话 ID")

    temperature: Optional[float] = Field(default=None, description="采样温度")
    max_tokens: Optional[int] = Field(default=None, description="最大输出 token")
    timeout: Optional[float] = Field(default=None, description="超时时间（秒）")
    thinking_enabled: Optional[bool] = Field(default=None, description="是否启用推理输出")
    react_mode_enabled: Optional[bool] = Field(default=None, description="是否启用 React 文本协议模式")
    history_messages: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="前端传入的会话历史（简化版），每项包含 role/content",
    )
    pending_code: Optional[str] = Field(
        default=None,
        description="前端当前未应用补丁对应的候选工作流代码（若有）",
    )


class WorkflowPatchOp(BaseModel):
    op: str = Field(description="补丁操作类型")
    target_node: Optional[str] = Field(default=None, description="目标节点变量名")
    new_code: Optional[str] = Field(default=None, description="整份工作流代码（replace_code 时使用）")
    new_block: Optional[str] = Field(default=None, description="插入的新节点块")
    new_meta: Optional[Dict[str, Any]] = Field(default=None, description="更新后的节点元数据字段")
    new_call: Optional[str] = Field(default=None, description="更新后的节点调用表达式")
    old_name: Optional[str] = Field(default=None, description="重命名前旧变量")
    new_name: Optional[str] = Field(default=None, description="重命名后新变量")
    reason: Optional[str] = Field(default=None, description="操作原因")


class WorkflowPatchRequest(BaseModel):
    base_revision: str = Field(description="补丁基线版本")
    patch_ops: List[WorkflowPatchOp] = Field(default_factory=list, description="补丁操作列表")
    dry_run: bool = Field(default=False, description="是否仅预览不落库")


class WorkflowPatchResponse(BaseModel):
    success: bool
    workflow_id: int
    base_revision: str
    new_revision: Optional[str] = None
    applied_ops: int = 0
    changed_nodes: List[str] = Field(default_factory=list)
    diff: str = ""
    new_code: str = ""
    parse_result: Dict[str, Any] = Field(default_factory=dict)
    validation: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
