
from sqlmodel import SQLModel
from typing import Optional

# 1. 定义基础模型 (Base Model)
class ProjectBase(SQLModel):
    name: str
    description: Optional[str] = None

# 2. 用于创建项目的模型 (Create Schema)
class ProjectCreate(ProjectBase):
    # 项目模板标识（如 "snowflake"），用于触发对应的初始化工作流
    # None 表示空白项目，不触发任何工作流
    template: Optional[str] = None

# 3. 用于从数据库读取项目的模型 (Read Schema)
class ProjectRead(ProjectBase):
    id: int

# 4. 用于更新项目的模型 (Update Schema)
class ProjectUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None 