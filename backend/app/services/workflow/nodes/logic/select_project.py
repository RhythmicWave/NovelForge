from typing import Any, Dict, AsyncIterator
from pydantic import Field, BaseModel
from loguru import logger
from sqlmodel import select

from app.db.models import Project
from ...registry import register_node
from ..base import BaseNode


class SelectProjectInput(BaseModel):
    """选择项目输入"""
    project_id: int = Field(
        ..., 
        description="项目ID",
        json_schema_extra={"x-component": "ProjectSelect"}
    )


class SelectProjectOutput(BaseModel):
    """选择项目输出"""
    project_id: int = Field(..., description="项目ID")
    project: Dict[str, Any] = Field(..., description="项目对象")


@register_node
class SelectProjectNode(BaseNode[SelectProjectInput, SelectProjectOutput]):
    node_type = "Logic.SelectProject"
    category = "logic"
    label = "选择项目"
    description = "选择项目"
    
    input_model = SelectProjectInput
    output_model = SelectProjectOutput

    async def execute(self, inputs: SelectProjectInput) -> AsyncIterator[SelectProjectOutput]:
        """选择项目节点"""
        # 验证项目是否存在
        project = self.context.session.get(Project, inputs.project_id)
        if not project:
            raise ValueError(f"项目不存在: {inputs.project_id}")
        
        logger.info(f"[SelectProject] 选择项目: {project.name} (id={inputs.project_id})")
        
        # 返回项目信息
        yield SelectProjectOutput(
            project_id=project.id,
            project={
                "id": project.id,
                "name": project.name,
                "description": project.description
            }
        )
