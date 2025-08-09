
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List

from app.db.session import get_session
from app.db.models import Chapter
from app.schemas.chapter import ChapterCreate, ChapterRead, ChapterUpdate
from app.schemas.response import ApiResponse

# Get a logger
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/", response_model=ApiResponse[ChapterRead], summary="创建新章节")
def create_chapter(chapter: ChapterCreate, db: Session = Depends(get_session)):
    logger.info(f"Received request to create chapter with data: {chapter.model_dump_json()}")

    db_chapter = Chapter.model_validate(chapter)
    logger.info(f"Validated chapter object (before add): {db_chapter}")

    db.add(db_chapter)
    logger.info("Chapter object added to session.")

    # Flush the session to assign an ID to db_chapter, making it persistent
    try:
        db.flush()
        logger.info(f"Session flushed. Chapter ID should now be available: {db_chapter.id}")
    except Exception as e:
        logger.error(f"Error during db.flush(): {e}", exc_info=True)
        raise

    # Now that the object is persistent, we can refresh it to get all default values
    try:
        db.refresh(db_chapter)
        logger.info(f"Chapter object refreshed. Final state: {db_chapter}")
    except Exception as e:
        logger.error(f"Error during db.refresh(): {e}", exc_info=True)
        raise

    return ApiResponse[ChapterRead](data=db_chapter)

@router.get("/by_volume/{volume_id}", response_model=ApiResponse[List[ChapterRead]], summary="根据分卷获取章节列表")
def get_chapters_by_volume(volume_id: int, db: Session = Depends(get_session)):
    chapters = db.exec(select(Chapter).where(Chapter.volume_id == volume_id)).all()
    return ApiResponse[List[ChapterRead]](data=chapters)

@router.get("/{chapter_id}", response_model=ApiResponse[ChapterRead], summary="获取单个章节")
def get_chapter(chapter_id: int, db: Session = Depends(get_session)):
    chapter = db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return ApiResponse[ChapterRead](data=chapter)

@router.put("/{chapter_id}", response_model=ApiResponse[ChapterRead], summary="更新章节")
def update_chapter(chapter_id: int, chapter: ChapterUpdate, db: Session = Depends(get_session)):
    db_chapter = db.get(Chapter, chapter_id)
    if not db_chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    chapter_data = chapter.model_dump(exclude_unset=True)
    for key, value in chapter_data.items():
        setattr(db_chapter, key, value)
    
    db.add(db_chapter)
    db.commit()  # 确保提交事务
    db.refresh(db_chapter)
    
    return ApiResponse[ChapterRead](data=db_chapter)

@router.delete("/{chapter_id}", response_model=ApiResponse, summary="删除章节")
def delete_chapter_endpoint(chapter_id: int, db: Session = Depends(get_session)):
    chapter = db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    db.delete(chapter)
    return ApiResponse(message="Chapter deleted successfully") 