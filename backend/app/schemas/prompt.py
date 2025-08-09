from typing import Optional

from sqlmodel import SQLModel, Field

class PromptBase(SQLModel):
    name: str = Field(index=True)
    description: Optional[str] = None
    template: str

class PromptRead(PromptBase):
    id: int

class PromptCreate(PromptBase):
    pass

class PromptUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template: Optional[str] = None 