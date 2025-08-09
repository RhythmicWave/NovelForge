
from sqlmodel import SQLModel
from typing import Optional, Dict, Any
from pydantic import BaseModel

class ChapterBase(BaseModel):
    title: str
    content: Optional[str] = None
    word_count: int = 0
    outline: Optional[dict] = None


class ChapterCreate(ChapterBase):
    pass


class ChapterUpdate(ChapterBase):
    title: Optional[str] = None
    content: Optional[str] = None
    word_count: Optional[int] = None
    outline: Optional[dict] = None


class ChapterRead(ChapterBase):
    id: int
    volume_id: Optional[int] = None
    outline: Optional[dict] = None

    class Config:
        from_attributes = True 