from typing import Any, Dict
from pydantic import Field
from loguru import logger
from sqlmodel import select

from app.db.models import Project
from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class SelectProjectConfig(BaseNodeConfig):
    project_id: int = Field(
        ..., 
        description="项目ID",
        json_schema_extra={"x-component": "ProjectSelect"}
    )


@register_node
class SelectProjectNode(BaseNode):
    node_type = "Logic.SelectProject"
    category = "logic"
    label = "选择项目"
    description = "选择项目并设置为全局变量"
    config_model = SelectProjectConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [],
            "outputs": [
                NodePort("project_id", "number", description="项目ID"),
                NodePort("project", "object", description="项目对象")
            ]
        }

    async def execute(self, inputs: Dict[str, Any], config: SelectProjectConfig) -> ExecutionResult:
        """选择项目节点"""
        project_id = config.project_id
        
        # 验证项目是否存在
        project = self.context.session.get(Project, project_id)
        if not project:
            return ExecutionResult(
                success=False,
                error=f"项目不存在: {project_id}"
            )
        
        # 设置全局变量
        self.context.variables["project_id"] = project_id
        self.context.variables["project"] = {
            "id": project.id,
            "name": project.name,
            "description": project.description
        }
        
        logger.info(f"[SelectProject] 选择项目: {project.name} (id={project_id})")
        
        return ExecutionResult(
            success=True,
            outputs={
                "project_id": project_id,
                "project": {
                    "id": project.id,
                    "name": project.name,
                    "description": project.description
                }
            }
        )
