"""上下文组装节点

复用 ContextService 为工作流提供上下文装配能力。
"""

from typing import Any, Dict, List, Optional
from pydantic import Field
from loguru import logger

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig
from app.services.context_service import assemble_context, ContextAssembleParams


class ContextAssembleConfig(BaseNodeConfig):
    """上下文组装配置"""
    
    project_id: Optional[int] = Field(
        None,
        description="项目 ID（留空则从全局变量获取）"
    )
    participants: List[str] = Field(
        default_factory=list,
        description="参与者列表（角色/地点名称）"
    )


@register_node
class ContextAssembleNode(BaseNode):
    """上下文组装节点"""
    
    node_type = "Context.Assemble"
    category = "context"
    label = "组装上下文"
    description = "从知识图谱中提取事实子图，为 LLM 提供结构化上下文"
    config_model = ContextAssembleConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [],
            "outputs": [
                NodePort("context_text", "string", description="格式化的上下文文本"),
                NodePort("context_data", "object", description="结构化上下文数据"),
            ]
        }

    async def execute(
        self,
        inputs: Dict[str, Any],
        config: ContextAssembleConfig
    ) -> ExecutionResult:
        """执行上下文组装"""
        
        # 获取项目 ID
        project_id = config.project_id
        if not project_id:
            project_id = self.context.variables.get("project_id")
            if not project_id:
                trigger = self.context.variables.get("trigger", {})
                project_id = trigger.get("project_id")
        
        if not project_id:
            return ExecutionResult(
                success=False,
                error="未找到项目 ID，请在配置中指定或确保触发器提供"
            )
        
        try:
            # 构建参数
            params = ContextAssembleParams(
                project_id=project_id,
                participants=config.participants,
                volume_number=None,
                chapter_number=None,
                current_draft_tail=None,
            )
            
            # 调用上下文服务
            result = assemble_context(self.context.session, params)
            
            logger.info(
                f"[Context.Assemble] 组装上下文成功: project_id={project_id}, "
                f"participants={config.participants}"
            )
            
            return ExecutionResult(
                success=True,
                outputs={
                    "context_text": result.facts_subgraph,
                    "context_data": result.facts_structured or {},
                }
            )
            
        except Exception as e:
            logger.error(f"[Context.Assemble] 组装上下文失败: {e}")
            return ExecutionResult(
                success=False,
                error=f"组装上下文失败: {str(e)}"
            )
