
from sqlmodel import SQLModel, Field, Relationship, Column, JSON
from typing import Optional, List, Any
from datetime import datetime


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None

    # Relations
    chapters: List["Chapter"] = Relationship(back_populates="project")
    cards: List["Card"] = Relationship(back_populates="project", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class Chapter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    content: Optional[str] = Field(default=None)
    outline: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    word_count: int = Field(default=0)

    # 仍保留 volume_id 作为分组字段，但不再建立外键关系（线性分卷已废弃）
    volume_id: Optional[int] = Field(default=None)
    project_id: int = Field(foreign_key="project.id")
    project: "Project" = Relationship(back_populates="chapters")


class LLMConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    display_name: Optional[str] = None
    model_name: str
    api_base: Optional[str] = None
    api_key: str
    base_url: Optional[str] = None


class Prompt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: Optional[str] = None
    template: str
    version: int = 1
    built_in: bool = Field(default=False)


# 输出模型库
# class OutputModel(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     # 模型唯一名称（作为 response_model_name）
#     name: str = Field(unique=True, index=True)
#     description: Optional[str] = None
#     # 存储完整 JSON Schema（解引用可在前端完成）
#     json_schema: Optional[dict] = Field(default=None, sa_column=Column(JSON))
#     built_in: bool = Field(default=False)
#     version: int = Field(default=1)
#     updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class CardType(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    # 兼容旧的模型名称（如 CharacterCard/SceneCard），为空则默认等于 name
    model_name: Optional[str] = Field(default=None, index=True)
    description: Optional[str] = None
    # 类型内置结构（JSON Schema）
    json_schema: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    # 类型级默认 AI 参数（模型ID/提示词/采样等）
    ai_params: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    editor_component: Optional[str] = None  # e.g., 'NovelEditor' for custom UI
    is_ai_enabled: bool = Field(default=True)
    is_singleton: bool = Field(default=False)  # e.g., only one 'Synopsis' card per project
    built_in: bool = Field(default=False)
    # 卡片类型级别的默认上下文注入模板
    default_ai_context_template: Optional[str] = Field(default=None)
    # UI 布局（可选），供前端 SectionedForm 使用
    ui_layout: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    cards: List["Card"] = Relationship(back_populates="card_type")


class Card(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    # 兼容旧的模型名称；为空表示跟随类型的 model_name 或类型名
    model_name: Optional[str] = Field(default=None, index=True)
    content: Any = Field(default={}, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    # 允许实例自定义结构；为空表示跟随类型
    json_schema: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    # 实例级 AI 参数；为空表示跟随类型
    ai_params: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    # 自引用关系，用于树形结构
    parent_id: Optional[int] = Field(default=None, foreign_key="card.id")
    parent: Optional["Card"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "[Card.id]"}
    )
    children: List["Card"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={
            "cascade": "all, delete, delete-orphan",
            "single_parent": True,
        },
    )

    # 项目外键
    project_id: int = Field(foreign_key="project.id")
    project: "Project" = Relationship(back_populates="cards")

    # Foreign key to CardType 卡片类型外键
    card_type_id: int = Field(foreign_key="cardtype.id")
    card_type: "CardType" = Relationship(back_populates="cards")

    # 用于排序卡片，用于同一父级下的排序
    display_order: int = Field(default=0)
    ai_context_template: Optional[str] = Field(default=None)


# 伏笔登记表
class ForeshadowItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    chapter_id: Optional[int] = Field(default=None)  # 章节卡片ID或章节ID
    title: str
    type: str = Field(default='other', index=True)  # goal | item | person | other
    note: Optional[str] = None
    status: str = Field(default='open', index=True)  # open | resolved
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    resolved_at: Optional[datetime] = None


# 知识库模型
class Knowledge(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: Optional[str] = None
    content: str
    built_in: bool = Field(default=False) 