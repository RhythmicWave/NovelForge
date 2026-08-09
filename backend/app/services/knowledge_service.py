from typing import List, Optional
from sqlmodel import Session, select
from app.db.models import Knowledge

class KnowledgeService:
    """知识库服务：提供知识库的增删改查。
    注意：内置（built_in=True）的知识库不允许删除，但允许编辑和重置。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, skip: int = 0, limit: Optional[int] = None) -> List[Knowledge]:
        """返回稳定排序的知识库列表；仅在显式传入 limit 时分页。"""
        statement = select(Knowledge).order_by(
            Knowledge.built_in.asc(),
            Knowledge.created_at.desc(),
            Knowledge.id.desc(),
        ).offset(skip)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.db.exec(statement).all())

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
            if not name.strip():
                raise ValueError("知识库名称不能为空")
            if getattr(kb, 'built_in', False) and name != kb.name:
                raise ValueError("系统内置知识库名称不允许修改")
        if name is not None:
            existing = self.get_by_name(name)
            if existing and existing.id != kb.id:
                raise ValueError(f"知识库名称 '{name}' 已存在")
            kb.name = name
        if description is not None:
            kb.description = description
        if content is not None:
            kb.content = content
        # 内置项被编辑时，自动标记为已修改
        if getattr(kb, 'built_in', False):
            kb.is_modified = True
        self.db.add(kb)
        self.db.commit()
        self.db.refresh(kb)
        return kb

    def reset(self, kid: int) -> Optional[Knowledge]:
        """重置内置知识库到原始状态"""
        kb = self.get_by_id(kid)
        if not kb:
            return None
        if not getattr(kb, 'built_in', False):
            raise ValueError("只能重置内置知识库")
        if kb.original_content is None:
            raise ValueError("该内置知识库缺少原始快照，无法重置")
        kb.content = kb.original_content
        kb.description = kb.original_description
        kb.is_modified = False
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
