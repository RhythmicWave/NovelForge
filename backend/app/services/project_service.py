
from typing import List, Optional
from sqlmodel import Session, select

from app.db.models import Project, Chapter
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.card_service import CardService

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
    
   
    CardService.create_initial_cards_for_project(session, db_project.id)
    
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
    session.delete(project)
    return True 