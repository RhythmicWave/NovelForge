from typing import List, Optional
from sqlmodel import Session, select
from app.db.models import Knowledge

class KnowledgeService:
    """知识库服务：提供知识库的增删改查。
    注意：内置（built_in=True）的知识库不允许删除。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, skip: int = 0, limit: int = 200) -> List[Knowledge]:
        return self.db.exec(select(Knowledge).offset(skip).limit(limit)).all()

    def get_by_id(self, kid: int) -> Optional[Knowledge]:
        return self.db.get(Knowledge, kid)

    def get_by_name(self, name: str) -> Optional[Knowledge]:
        return self.db.exec(select(Knowledge).where(Knowledge.name == name)).first()

    def create(self, name: str, content: str, description: Optional[str] = None, built_in: bool = False) -> Knowledge:
        kb = Knowledge(name=name, content=content, description=description, built_in=built_in)
        self.db.add(kb)
        self.db.commit()
        self.db.refresh(kb)
        return kb

    def update(self, kid: int, name: Optional[str] = None, content: Optional[str] = None, description: Optional[str] = None) -> Optional[Knowledge]:
        kb = self.get_by_id(kid)
        if not kb:
            return None
        if name is not None:
            kb.name = name
        if description is not None:
            kb.description = description
        if content is not None:
            kb.content = content
        self.db.add(kb)
        self.db.commit()
        self.db.refresh(kb)
        return kb

    def delete(self, kid: int) -> bool:
        kb = self.get_by_id(kid)
        if not kb:
            return False
        if getattr(kb, 'built_in', False):
            raise ValueError("系统内置知识库不可删除")
        self.db.delete(kb)
        self.db.commit()
        return True 