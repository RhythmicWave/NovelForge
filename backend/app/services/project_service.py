
from typing import List, Optional, Tuple
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




from typing import List, Optional, Tuple

def create_project(session: Session, project_in: ProjectCreate) -> Tuple[Project, List[int]]:
    # 检查项目名称是否已存在
    from sqlmodel import select
    existing_project = session.exec(
        select(Project).where(Project.name == project_in.name)
    ).first()
    
    if existing_project:
        raise ValueError(f"项目名称已存在: {project_in.name}")
    
    db_project = Project.model_validate(project_in)
    session.add(db_project)
    session.commit()
    session.refresh(db_project)
    
    triggered_run_ids = []
    # 触发项目创建事件
    try:
        from app.core import emit_event
        
        event_data = {
            "session": session,
            "project_id": db_project.id,
            "template": project_in.template,  # 传递模板标识
        }
        
        emit_event("project.created", event_data)
        triggered_run_ids = event_data.get("triggered_run_ids", [])
    except Exception:
        # 不阻断项目创建
        pass
    
    # 刷新以加载新创建的卡片到项目关系中
    session.refresh(db_project)
    
    return db_project, triggered_run_ids


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