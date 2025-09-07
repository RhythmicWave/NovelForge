from typing import List, Optional
from sqlmodel import Session, select
from app.db.models import ProjectTemplate, ProjectTemplateItem

class ProjectTemplateService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, skip: int = 0, limit: int = 200) -> List[ProjectTemplate]:
        return self.db.exec(select(ProjectTemplate).offset(skip).limit(limit)).all()

    def get_by_id(self, tid: int) -> Optional[ProjectTemplate]:
        return self.db.get(ProjectTemplate, tid)

    def get_by_name(self, name: str) -> Optional[ProjectTemplate]:
        return self.db.exec(select(ProjectTemplate).where(ProjectTemplate.name == name)).first()

    def create(self, name: str, description: Optional[str], items: List[dict], built_in: bool = False) -> ProjectTemplate:
        tpl = ProjectTemplate(name=name, description=description, built_in=built_in)
        self.db.add(tpl)
        self.db.flush()
        # 添加条目
        for i in items or []:
            it = ProjectTemplateItem(
                template_id=tpl.id,
                card_type_id=i['card_type_id'],
                display_order=i.get('display_order', 0),
                title_override=i.get('title_override')
            )
            self.db.add(it)
        self.db.commit()
        self.db.refresh(tpl)
        return tpl

    def update(self, tid: int, name: Optional[str] = None, description: Optional[str] = None, items: Optional[List[dict]] = None) -> Optional[ProjectTemplate]:
        tpl = self.get_by_id(tid)
        if not tpl:
            return None
        if name is not None:
            tpl.name = name
        if description is not None:
            tpl.description = description
        self.db.add(tpl)
        # 重建条目（简单策略）
        if items is not None:
            # 删除旧项
            self.db.exec(select(ProjectTemplateItem).where(ProjectTemplateItem.template_id == tpl.id))
            self.db.query(ProjectTemplateItem).filter(ProjectTemplateItem.template_id == tpl.id)
            # 直接删除并重建
            for old in self.db.exec(select(ProjectTemplateItem).where(ProjectTemplateItem.template_id == tpl.id)).all():
                self.db.delete(old)
            self.db.flush()
            for i in items:
                it = ProjectTemplateItem(
                    template_id=tpl.id,
                    card_type_id=i['card_type_id'],
                    display_order=i.get('display_order', 0),
                    title_override=i.get('title_override')
                )
                self.db.add(it)
        self.db.commit()
        self.db.refresh(tpl)
        return tpl

    def delete(self, tid: int) -> bool:
        tpl = self.get_by_id(tid)
        if not tpl:
            return False
        # if getattr(tpl, 'built_in', False):
        #     raise ValueError("系统内置项目模板不可删除")
        # 条目随模板级联删除
        self.db.delete(tpl)
        self.db.commit()
        return True 