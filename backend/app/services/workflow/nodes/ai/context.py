"""上下文组装节点

复用 ContextService 为工作流提供上下文装配能力。
"""

from typing import Any, Dict, List, Optional, AsyncIterator
from pydantic import BaseModel, Field
from loguru import logger

from ...registry import register_node
from ..base import BaseNode
from app.services.context_service import assemble_context, ContextAssembleParams


class ContextAssembleInput(BaseModel):
    """上下文组装输入"""
    
    project_id: int = Field(..., description="项目ID（必须显式传递）")
    participants: List[str] = Field(
        default_factory=list,
        description="参与者列表（角色/地点名称）"
    )


class ContextAssembleOutput(BaseModel):
    """上下文组装输出"""
    
    context_text: str = Field(..., description="格式化的上下文文本")
    context_data: Dict[str, Any] = Field(default_factory=dict, description="结构化上下文数据")


#未经校验，暂时不显示
# @register_node
class ContextAssembleNode(BaseNode):
    """上下文组装节点"""
    
    node_type = "Context.Assemble"
    category = "context"
    label = "组装上下文"
    description = "从知识图谱中提取事实子图，为 LLM 提供结构化上下文"
    input_model = ContextAssembleInput
    output_model = ContextAssembleOutput

    async def execute(self, input_data: ContextAssembleInput) -> AsyncIterator[ContextAssembleOutput]:
        """执行上下文组装"""
        
        # 使用显式传递的项目ID
        project_id = input_data.project_id
        
        # 构建参数
        params = ContextAssembleParams(
            project_id=project_id,
            participants=input_data.participants,
            volume_number=None,
            chapter_number=None,
            current_draft_tail=None,
        )
        
        # 调用上下文服务
        result = assemble_context(self.context.session, params)
        
        logger.info(
            f"[Context.Assemble] 组装上下文成功: project_id={project_id}, "
            f"participants={input_data.participants}"
        )
        
        yield ContextAssembleOutput(
            context_text=result.facts_subgraph,
            context_data=result.facts_structured or {},
        )
