import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from datetime import datetime
from sqlmodel import SQLModel, Session, create_engine, select, text

from app.db.models import Prompt, Knowledge
from app.schemas.prompt import PromptUpdate
from app.services.prompt_service import (
    get_prompts,
    update_prompt,
    reset_prompt,
)
from app.services.knowledge_service import KnowledgeService
from app.bootstrap.prompts import init_prompts
from app.bootstrap.knowledge import init_knowledge
from app.core.startup import _ensure_safe_additive_columns


@pytest.fixture(name="engine")
def engine_fixture():
    # 使用内存 SQLite 数据库进行独立单元测试
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    yield engine


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session


def test_old_database_column_autofill(monkeypatch):
    """测试旧数据库升级：缺乏 is_modified, created_at, built_in 列时，启动增量补列成功"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    
    # 模拟旧版本数据库（没有 built_in, is_modified, created_at, original_* 列）
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE prompt (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR NOT NULL,
                description VARCHAR,
                template VARCHAR NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            );
        """))
        conn.execute(text("""
            CREATE TABLE knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR NOT NULL,
                description VARCHAR,
                content VARCHAR NOT NULL
            );
        """))
        conn.execute(text("""
            INSERT INTO prompt (name, description, template) VALUES ('old_prompt', 'desc', 'template_v1');
        """))
        conn.execute(text("""
            INSERT INTO knowledge (name, description, content) VALUES ('old_kb', 'desc', 'content_v1');
        """))

    # 将 app.core.startup.engine 和 app.db.session.engine monkeypatch 为测试内存 engine
    monkeypatch.setattr("app.core.startup.engine", engine)
    monkeypatch.setattr("app.db.session.engine", engine)
    _ensure_safe_additive_columns()

    # 验证补列后可以成功用 SQLModel ORM 完整查出旧数据，无 missing column 异常
    with Session(engine) as session:
        prompts = session.exec(select(Prompt)).all()
        assert len(prompts) == 1
        assert prompts[0].name == "old_prompt"
        assert prompts[0].is_modified is False
        assert isinstance(prompts[0].created_at, datetime)

        kbs = session.exec(select(Knowledge)).all()
        assert len(kbs) == 1
        assert kbs[0].name == "old_kb"
        assert kbs[0].is_modified is False
        assert isinstance(kbs[0].created_at, datetime)


def test_bootstrap_overwrite_modes(session, monkeypatch):
    """测试 BOOTSTRAP_OVERWRITE 在 True 和 False 下的更新行为"""
    # 1. 运行初始化 (overwrite=True)
    monkeypatch.setattr("app.core.config.settings.bootstrap.overwrite", True)
    init_prompts(session)
    init_knowledge(session)

    prompt = session.exec(select(Prompt).where(Prompt.built_in == True)).first()
    assert prompt is not None
    assert prompt.original_template == prompt.template
    assert prompt.is_modified is False

    kb = session.exec(select(Knowledge).where(Knowledge.built_in == True)).first()
    assert kb is not None
    assert kb.original_content == kb.content
    assert kb.is_modified is False

    # 2. 用户修改内置项内容
    prompt.template = "User Modified Template"
    prompt.is_modified = True
    session.add(prompt)

    kb.content = "User Modified Content"
    kb.is_modified = True
    session.add(kb)
    session.commit()

    # 3. 模拟在 overwrite=False 下重新启动 Bootstrap
    monkeypatch.setattr("app.core.config.settings.bootstrap.overwrite", False)
    init_prompts(session)
    init_knowledge(session)

    session.refresh(prompt)
    session.refresh(kb)

    # 校验：overwrite=False 时保留用户修改的 template，但 original_template 保持原始种子快照
    assert prompt.template == "User Modified Template"
    assert prompt.original_template != "User Modified Template"
    assert prompt.is_modified is True

    assert kb.content == "User Modified Content"
    assert kb.original_content != "User Modified Content"
    assert kb.is_modified is True

    # 4. 模拟在 overwrite=True 下重新启动 Bootstrap
    monkeypatch.setattr("app.core.config.settings.bootstrap.overwrite", True)
    init_prompts(session)
    init_knowledge(session)

    session.refresh(prompt)
    session.refresh(kb)

    # 校验：overwrite=True 时覆盖为种子数据，并且 is_modified 被重置为 False
    assert prompt.template == prompt.original_template
    assert prompt.is_modified is False

    assert kb.content == kb.original_content
    assert kb.is_modified is False


def test_builtin_edit_and_reset(session):
    """测试内置项修改与 reset 功能（包括 null 描述情况的还原）"""
    # 初始化内置提示词和知识库
    p = Prompt(
        name="test_builtin_prompt",
        description=None,  # 原始 description 为 None
        template="Original Template",
        original_template="Original Template",
        original_description=None,
        built_in=True,
        is_modified=False,
    )
    kb = Knowledge(
        name="test_builtin_kb",
        description="Original KB Desc",
        content="Original Content",
        original_content="Original Content",
        original_description="Original KB Desc",
        built_in=True,
        is_modified=False,
    )
    session.add(p)
    session.add(kb)
    session.commit()

    # 修改 Prompt
    update_prompt(session, p.id, PromptUpdate(description="New Desc", template="New Template"))
    session.refresh(p)
    assert p.is_modified is True
    assert p.template == "New Template"
    assert p.description == "New Desc"

    # 重置 Prompt
    reset_prompt(session, p.id)
    session.refresh(p)
    assert p.is_modified is False
    assert p.template == "Original Template"
    assert p.description is None  # 正确恢复为空（None）而不是保留 New Desc

    # 修改 Knowledge
    svc = KnowledgeService(session)
    svc.update(kb.id, description="New KB Desc", content="New Content")
    session.refresh(kb)
    assert kb.is_modified is True

    # 重置 Knowledge
    svc.reset(kb.id)
    session.refresh(kb)
    assert kb.is_modified is False
    assert kb.content == "Original Content"
    assert kb.description == "Original KB Desc"


def test_builtin_rename_prohibited(session):
    """测试禁止修改内置提示词和内置知识库的名称"""
    p = Prompt(
        name="builtin_prompt_fixed",
        template="Template",
        built_in=True,
    )
    kb = Knowledge(
        name="builtin_kb_fixed",
        content="Content",
        built_in=True,
    )
    session.add(p)
    session.add(kb)
    session.commit()

    # 尝试修改 Built-in Prompt 名称
    with pytest.raises(ValueError, match="系统内置提示词名称不允许修改"):
        update_prompt(session, p.id, PromptUpdate(name="renamed_prompt"))

    # 尝试修改 Built-in Knowledge 名称
    svc = KnowledgeService(session)
    with pytest.raises(ValueError, match="系统内置知识库名称不允许修改"):
        svc.update(kb.id, name="renamed_kb")


def test_custom_items_limit_does_not_truncate_builtin(session):
    """测试自定义项超限时，列表接口仍能完整返回所有内置项"""
    # 创建 1 个内置 Prompt 和 105 个自定义 Prompt
    builtin_p = Prompt(name="builtin_p", template="Template", built_in=True)
    session.add(builtin_p)
    for i in range(105):
        session.add(Prompt(name=f"custom_p_{i}", template="Template", built_in=False))

    # 创建 1 个内置 Knowledge 和 105 个自定义 Knowledge
    builtin_kb = Knowledge(name="builtin_kb", content="Content", built_in=True)
    session.add(builtin_kb)
    for i in range(105):
        session.add(Knowledge(name=f"custom_kb_{i}", content="Content", built_in=False))
    
    session.commit()

    # 查询 Prompt 列表 (limit=100)
    prompts = get_prompts(session, limit=100)
    # 应包含 100 个自定义项 + 1 个内置项 = 101 项
    assert len(prompts) == 101
    assert any(p.name == "builtin_p" for p in prompts)

    # 查询 Knowledge 列表 (limit=100)
    svc = KnowledgeService(session)
    kbs = svc.list(limit=100)
    assert len(kbs) == 101
    assert any(k.name == "builtin_kb" for k in kbs)
