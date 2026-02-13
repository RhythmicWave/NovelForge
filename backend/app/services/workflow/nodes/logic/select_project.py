from typing import Any, AsyncIterator, Dict

from loguru import logger
from pydantic import BaseModel, Field
from sqlmodel import select

from app.db.models import Project
from ...registry import register_node
from ..base import BaseNode


class SelectProjectInput(BaseModel):
    """选择项目输入"""

    project_id: int | None = Field(
        default=None,
        description="项目ID",
        json_schema_extra={"x-component": "ProjectSelect"},
    )
    project_name: str | None = Field(
        default=None,
        description="项目名称（当 project_id 为空时按名称解析，名称和ID提供一个即可）",
        json_schema_extra={"x-component": "ProjectSelect"},
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
    description = "选择并输出一个项目，可以根据名字、ID来获取具体的项目，返回结果中包括项目ID"

    input_model = SelectProjectInput
    output_model = SelectProjectOutput

    async def execute(self, inputs: SelectProjectInput) -> AsyncIterator[SelectProjectOutput]:
        session = self.context.session

        project = None
        if inputs.project_id is not None:
            project = session.get(Project, inputs.project_id)

        if project is None and inputs.project_name:
            project = session.exec(
                select(Project).where(Project.name == inputs.project_name)
            ).first()
            if project is None:
                candidates = session.exec(select(Project)).all()
                lowered = inputs.project_name.lower()
                matches = [
                    item
                    for item in candidates
                    if lowered in (item.name or "").lower()
                ]
                if len(matches) == 1:
                    project = matches[0]
                elif len(matches) > 1:
                    raise ValueError(
                        f"项目名匹配到多个候选: {inputs.project_name}"
                    )

        if not project:
            raise ValueError(
                f"项目不存在: id={inputs.project_id}, name={inputs.project_name}"
            )

        logger.info(f"[SelectProject] 选择项目: {project.name} (id={project.id})")

        yield SelectProjectOutput(
            project_id=project.id,
            project={
                "id": project.id,
                "name": project.name,
                "description": project.description,
            },
        )
