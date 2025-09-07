from typing import Optional
from sqlmodel import SQLModel

class ProjectTemplateItemBase(SQLModel):
    card_type_id: int
    display_order: int = 0
    title_override: Optional[str] = None

class ProjectTemplateItemRead(ProjectTemplateItemBase):
    id: int

class ProjectTemplateItemCreate(ProjectTemplateItemBase):
    pass

class ProjectTemplateBase(SQLModel):
    name: str
    description: Optional[str] = None
    built_in: bool = False

class ProjectTemplateRead(ProjectTemplateBase):
    id: int
    items: list[ProjectTemplateItemRead] = []

class ProjectTemplateCreate(ProjectTemplateBase):
    items: list[ProjectTemplateItemCreate] = []

class ProjectTemplateUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    items: Optional[list[ProjectTemplateItemCreate]] = None 