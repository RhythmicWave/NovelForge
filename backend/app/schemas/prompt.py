from typing import Optional

from sqlmodel import SQLModel, Field

class PromptBase(SQLModel):
    name: str = Field(index=True)
    description: Optional[str] = None
    template: str

class PromptRead(PromptBase):
    id: int
    built_in: bool = False

class PromptCreate(PromptBase):
    pass

class PromptUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template: Optional[str] = None

# 知识库Schema
class KnowledgeBase(SQLModel):
    name: str
    description: Optional[str] = None
    content: str
    built_in: bool = False

class KnowledgeRead(KnowledgeBase):
    id: int

class KnowledgeCreate(SQLModel):
    name: str
    description: Optional[str] = None
    content: str

class KnowledgeUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None 