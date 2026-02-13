
from sqlmodel import SQLModel, Field, Relationship, Column, JSON
from sqlalchemy import UniqueConstraint
import sqlalchemy as sa
from typing import Optional, List, Any
from datetime import datetime


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: Optional[str] = None

    cards: List["Card"] = Relationship(back_populates="project", sa_relationship_kwargs={"cascade": "all, delete-orphan"})



class LLMConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    display_name: Optional[str] = None
    model_name: str
    api_base: Optional[str] = None
    api_key: str
    base_url: Optional[str] = None
    # 统计与配额（-1 表示不限）——在 DB 层也设置 server_default，便于 Alembic 自动包含
    token_limit: int = Field(
        default=-1,
        sa_column=Column(sa.Integer, nullable=False, server_default='-1')
    )
    call_limit: int = Field(
        default=-1,
        sa_column=Column(sa.Integer, nullable=False, server_default='-1')
    )
    used_tokens_input: int = Field(
        default=0,
        sa_column=Column(sa.Integer, nullable=False, server_default='0')
    )
    used_tokens_output: int = Field(
        default=0,
        sa_column=Column(sa.Integer, nullable=False, server_default='0')
    )
    used_calls: int = Field(
        default=0,
        sa_column=Column(sa.Integer, nullable=False, server_default='0')
    )
    # RPM/TPM 仅占位，暂不实现
    rpm_limit: int = Field(
        default=-1,
        sa_column=Column(sa.Integer, nullable=False, server_default='-1')
    )
    tpm_limit: int = Field(
        default=-1,
        sa_column=Column(sa.Integer, nullable=False, server_default='-1')
    )


class Prompt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: Optional[str] = None
    template: str
    version: int = 1
    built_in: bool = Field(default=False)



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
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)

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

    # 卡片类型外键
    card_type_id: int = Field(foreign_key="cardtype.id")
    card_type: "CardType" = Relationship(back_populates="cards")

    # 用于排序卡片，用于同一父级下的排序
    display_order: int = Field(default=0)
    ai_context_template: Optional[str] = Field(default=None)
    
    # AI 修改状态标记
    ai_modified: bool = Field(default=False)  # 是否由AI修改过
    needs_confirmation: bool = Field(default=False)  # 是否需要用户确认（用于触发工作流）
    last_modified_by: Optional[str] = Field(default=None)  # 最后修改者：'user' | 'ai' | None


# 伏笔登记表
class ForeshadowItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    chapter_id: Optional[int] = Field(default=None)  # 章节卡片ID或章节ID
    title: str
    type: str = Field(default='other', index=True)  # goal | item | person | other
    note: Optional[str] = None
    status: str = Field(default='open', index=True)  # open | resolved
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    resolved_at: Optional[datetime] = None


# 知识库模型
class Knowledge(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: Optional[str] = None
    content: str
    built_in: bool = Field(default=False)


# 工作流系统
class Workflow(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    dsl_version: int = Field(default=2)  # DSL版本：2=代码式工作流
    is_built_in: bool = Field(default=False)
    is_active: bool = Field(default=True)
    
    # 工作流定义（代码式）
    definition_code: str = Field(default="")  # 工作流代码
    
    # 工作流模板
    is_template: bool = Field(default=False)
    template_category: Optional[str] = None  # 如："内容生成"、"数据处理"
    
    # 运行数据保留策略
    # True: 长期保留（受全局有效期限制）
    # False: 短期保留（仅用于前端查看结果，之后自动清理）
    keep_run_history: bool = Field(default=False)
    
    # 触发器缓存（优化性能，避免单独查询 WorkflowTrigger 表）
    triggers_cache: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    """触发器缓存（从代码中自动提取）
    
    结构：
    [
        {
            "trigger_on": "onsave",           # 触发事件类型
            "card_type_name": "章节",         # 卡片类型（可选）
            "filter_json": {                  # 过滤配置（可选）
                "events": ["create", "update"],
                "conditions": [...]
            }
        },
        ...
    ]
    
    优势：
    - 启动性能提升 100 倍（5ms vs 500ms）
    - 避免数据冗余和同步问题
    - 代码是唯一真实来源
    """
    
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.now, nullable=False)

    # Relations
    runs: List["WorkflowRun"] = Relationship(back_populates="workflow", sa_relationship_kwargs={
        "cascade": "all, delete-orphan"
    })


class WorkflowRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    workflow_id: int = Field(foreign_key="workflow.id")
    workflow: Workflow = Relationship(back_populates="runs")

    definition_version: int = Field(default=1)
    # queued | running | succeeded | failed | cancelled | paused | timeout
    status: str = Field(default="queued", index=True)
    scope_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    params_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    idempotency_key: Optional[str] = Field(default=None, index=True)
    
    # 执行状态
    state_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))  # 运行时状态（变量、节点输出等）
    error_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))  # 错误信息
    
    # 时间控制
    max_execution_time: Optional[int] = None  # 秒，None表示无限制
    
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    summary_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Relations
    node_states: List["NodeExecutionState"] = Relationship(back_populates="run", sa_relationship_kwargs={
        "cascade": "all, delete-orphan"
    })


class NodeExecutionState(SQLModel, table=True):
    """节点执行状态表 - 用于详细追踪每个节点的执行情况"""
    __tablename__ = "nodeexecutionstate"
    __table_args__ = (
        # 添加唯一约束：同一个 run 的同一个节点只能有一条记录
        UniqueConstraint('run_id', 'node_id', name='uq_run_node'),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="workflowrun.id", index=True)
    run: WorkflowRun = Relationship(back_populates="node_states")

    node_id: str = Field(index=True)  # 节点ID（来自DSL）
    node_type: str  # 节点类型

    # 执行状态：idle | pending | running | success | error | skipped
    status: str = Field(default="idle", index=True)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    progress: int = Field(default=0)  # 0-100
    
    # 节点输出（用于断点续传）
    outputs_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    """节点输出数据（用于恢复执行）
    
    当工作流暂停后恢复时，需要从这里读取已完成节点的输出，
    以便后续节点可以访问前置节点的结果。
    
    示例：
    {
        "project_id": 123,
        "card_id": 456,
        "result": {...}
    }
    """
    
    # 错误信息（简化）
    error_message: Optional[str] = None
    
    # 检查点数据（新增）
    checkpoint_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    """检查点数据（轻量级元数据）
    
    结构：
    {
        "percent": 50.0,                    # 进度百分比
        "message": "已处理 30/60",          # 进度消息
        "data": {                           # 节点自定义数据（可选）
            "processed_count": 30,          # ✅ 轻量级：计数器
            "last_item_id": "item_30",      # ✅ 轻量级：标识符
            "current_batch": 3              # ✅ 轻量级：批次号
        },
        "timestamp": "2026-02-04T10:30:00"  # 保存时间
    }
    
    注意：
    - data 字段只保存位置信息，不保存业务数据
    - 大小限制：< 10KB
    - 用于断点续传，节点通过 context.checkpoint 访问
    """
    
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.now, nullable=False)