
from sqlmodel import SQLModel
from typing import Optional

# 1. 定义基础模型 (Base Model)
class ProjectBase(SQLModel):
    name: str
    description: Optional[str] = None

# 2. 用于创建项目的模型 (Create Schema)
class ProjectCreate(ProjectBase):
    # 创建项目时可选择模板
    template_id: Optional[int] = None

# 3. 用于从数据库读取项目的模型 (Read Schema)
class ProjectRead(ProjectBase):
    id: int

# 4. 用于更新项目的模型 (Update Schema)
class ProjectUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None 