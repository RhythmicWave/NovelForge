
from sqlmodel import SQLModel
from typing import Optional

class LLMConfigBase(SQLModel):
    provider: str
    display_name: Optional[str] = None
    model_name: str
    api_base: Optional[str] = None
    api_key: Optional[str] = None

class LLMConfigCreate(LLMConfigBase):
    pass

class LLMConfigRead(LLMConfigBase):
    id: int

class LLMConfigUpdate(SQLModel):
    provider: Optional[str] = None
    display_name: Optional[str] = None
    model_name: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None

class LLMConnectionTest(SQLModel):
    provider: str
    model_name: str
    api_base: Optional[str] = None
    api_key: str 