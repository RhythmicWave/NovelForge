"""保留项目初始化

初始化系统保留项目。
"""

from sqlmodel import Session, select
from loguru import logger

from app.db.models import Project
from .registry import initializer


@initializer(name="保留项目", order=40)
def init_reserved_project(session: Session) -> None:
    """初始化保留项目
    
    确保存在一个保留项目 __free__，用于跨项目的自由卡片归档。
    
    Args:
        session: 数据库会话
    """
    FREE_NAME = "__free__"
    exists = session.exec(select(Project).where(Project.name == FREE_NAME)).first()
    if not exists:
        p = Project(name=FREE_NAME, description="系统保留项目：存放自由卡片")
        session.add(p)
        session.commit()
        session.refresh(p)
        logger.info(f"已创建保留项目: {FREE_NAME} (id={p.id})")
    else:
        # 可在此处做增量更新（如描述字段）
        pass
