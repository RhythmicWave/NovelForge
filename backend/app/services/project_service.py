
from typing import List, Optional
from sqlmodel import Session, select

from app.db.models import Project, Workflow
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.card_service import CardService
from app.services.kg_provider import get_provider


FREE_PROJECT_NAME = "__free__"

# 获取或创建保留项目（__free__）
def get_or_create_free_project(session: Session) -> Project:
    proj = session.exec(select(Project).where(Project.name == FREE_PROJECT_NAME)).first()
    if proj:
        return proj
    proj = Project(name=FREE_PROJECT_NAME, description="系统保留项目：存放自由卡片")
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return proj


def get_projects(session: Session) -> List[Project]:
    statement = select(Project).order_by(Project.id.desc())
    return session.exec(statement).all()


def get_project(session: Session, project_id: int) -> Optional[Project]:
    statement = (
        select(Project)
        .where(Project.id == project_id)
    )
    return session.exec(statement).first()




def create_project(session: Session, project_in: ProjectCreate) -> Project:
    db_project = Project.model_validate(project_in)
    session.add(db_project)
    session.commit()
    session.refresh(db_project)
    
    # 如果传入的是 workflow_id，则直接运行该工作流
    workflow_id = getattr(project_in, 'workflow_id', None)
    if isinstance(workflow_id, int) and workflow_id > 0:
        wf = session.get(Workflow, workflow_id)
        if wf:
            # 直接创建一次运行，作用域仅携带 project_id
            from app.services.workflow_engine import engine as wf_engine
            run = wf_engine.create_run(session, wf, scope_json={"project_id": db_project.id}, params_json={}, idempotency_key=f"proj-init:{db_project.id}:{workflow_id}")
            wf_engine.run(session, run)
    else:
        # 触发所有 onprojectcreate 工作流
        try:
            from app.core import emit_event
            emit_event("project.created", {"session": session, "project_id": db_project.id})
        except Exception:
            # 不阻断项目创建
            pass
    
    # 刷新以加载新创建的卡片到项目关系中
    session.refresh(db_project)
    
    return db_project


def update_project(session: Session, project_id: int, project_in: ProjectUpdate) -> Optional[Project]:
    db_project = session.get(Project, project_id)
    if not db_project:
        return None
    project_data = project_in.model_dump(exclude_unset=True)
    for key, value in project_data.items():
        setattr(db_project, key, value)
    session.add(db_project)
    session.flush()
    session.refresh(db_project)
    return db_project


def delete_project(session: Session, project_id: int) -> bool:
    project = session.get(Project, project_id)
    if not project:
        return False
    # 保留项目禁止删除
    if getattr(project, 'name', None) == FREE_PROJECT_NAME:
        return False
    # 先删除数据库中的项目记录
    session.delete(project)
    session.commit()
    # 再清理图数据库中该项目的所有实体与关系
    try:
        kg = get_provider()
        kg.delete_project_graph(project_id)
    except Exception:
        # 避免图数据库不可用时影响主流程
        pass
    return True 