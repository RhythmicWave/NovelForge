
from typing import List, Optional
from sqlmodel import Session, select
from app.db.models import Chapter
from app.schemas.chapter import ChapterCreate, ChapterUpdate

def get_chapter(session: Session, chapter_id: int) -> Optional[Chapter]:
    """根据ID获取单个章节"""
    return session.get(Chapter, chapter_id)

def get_chapters_by_volume(session: Session, volume_id: int) -> List[Chapter]:
    """根据分卷ID获取章节列表"""
    statement = select(Chapter).where(Chapter.volume_id == volume_id)
    return session.exec(statement).all()

def create_chapter(session: Session, chapter_create: ChapterCreate) -> Chapter:
    """创建新章节"""
    db_chapter = Chapter.model_validate(chapter_create)
    session.add(db_chapter)
    session.commit()
    session.refresh(db_chapter)
    return db_chapter

def update_chapter(session: Session, chapter_id: int, chapter_update: ChapterUpdate) -> Optional[Chapter]:
    db_chapter = session.get(Chapter, chapter_id)
    if not db_chapter:
        return None
    
    update_data = chapter_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_chapter, key, value)
    
    session.add(db_chapter)
    session.commit()
    session.refresh(db_chapter)
    return db_chapter

def delete_chapter(session: Session, chapter_id: int) -> bool:
    db_chapter = session.get(Chapter, chapter_id)
    if not db_chapter:
        return False
    
    session.delete(db_chapter)
    session.commit()
    return True 