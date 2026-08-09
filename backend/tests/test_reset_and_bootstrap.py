import os
import sys
from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine, select, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.endpoints import knowledge as knowledge_endpoints
from app.api.endpoints import prompts as prompt_endpoints
from app.bootstrap.knowledge import init_knowledge
from app.bootstrap.prompts import init_prompts
from app.core.startup import _ensure_safe_additive_columns
from app.db.models import Knowledge, Prompt
from app.schemas.prompt import PromptCreate, PromptUpdate
from app.services.knowledge_service import KnowledgeService
from app.services.prompt_service import get_prompts, reset_prompt, update_prompt


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    yield engine


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session


def test_old_database_column_autofill(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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
        conn.execute(text("INSERT INTO prompt (name, description, template) VALUES ('old_prompt', 'desc', 'template_v1');"))
        conn.execute(text("INSERT INTO knowledge (name, description, content) VALUES ('old_kb', 'desc', 'content_v1');"))

    monkeypatch.setattr("app.core.startup.engine", engine)
    monkeypatch.setattr("app.db.session.engine", engine)
    _ensure_safe_additive_columns()

    with Session(engine) as session:
        prompt = session.exec(select(Prompt)).one()
        assert prompt.name == "old_prompt"
        assert prompt.is_modified is False
        assert isinstance(prompt.created_at, datetime)

        knowledge = session.exec(select(Knowledge)).one()
        assert knowledge.name == "old_kb"
        assert knowledge.is_modified is False
        assert isinstance(knowledge.created_at, datetime)


def test_bootstrap_overwrite_modes(session, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.bootstrap.overwrite", True)
    init_prompts(session)
    init_knowledge(session)

    prompt = session.exec(select(Prompt).where(Prompt.built_in == True)).first()
    knowledge = session.exec(select(Knowledge).where(Knowledge.built_in == True)).first()
    assert prompt is not None
    assert knowledge is not None
    assert prompt.original_template == prompt.template
    assert knowledge.original_content == knowledge.content
    assert prompt.is_modified is False
    assert knowledge.is_modified is False

    prompt.template = "User Modified Template"
    prompt.is_modified = True
    knowledge.content = "User Modified Content"
    knowledge.is_modified = True
    session.commit()

    monkeypatch.setattr("app.core.config.settings.bootstrap.overwrite", False)
    init_prompts(session)
    init_knowledge(session)
    session.refresh(prompt)
    session.refresh(knowledge)
    assert prompt.template == "User Modified Template"
    assert prompt.is_modified is True
    assert knowledge.content == "User Modified Content"
    assert knowledge.is_modified is True

    monkeypatch.setattr("app.core.config.settings.bootstrap.overwrite", True)
    init_prompts(session)
    init_knowledge(session)
    session.refresh(prompt)
    session.refresh(knowledge)
    assert prompt.template == prompt.original_template
    assert knowledge.content == knowledge.original_content
    assert prompt.is_modified is False
    assert knowledge.is_modified is False


def test_bootstrap_does_not_take_over_different_custom_items(session, monkeypatch):
    prompt_seed = {"name": "collision", "description": "seed description", "template": "seed template"}
    knowledge_seed = {"name": "collision", "description": "seed description", "content": "seed content"}
    custom_prompt = Prompt(
        name="collision",
        description="custom description",
        template="custom template",
        original_description="custom snapshot",
        original_template="custom snapshot",
        built_in=False,
        is_modified=True,
    )
    custom_knowledge = Knowledge(
        name="collision",
        description="custom description",
        content="custom content",
        original_description="custom snapshot",
        original_content="custom snapshot",
        built_in=False,
        is_modified=True,
    )
    session.add_all([custom_prompt, custom_knowledge])
    session.commit()

    monkeypatch.setattr("app.core.config.settings.bootstrap.overwrite", False)
    monkeypatch.setattr("app.bootstrap.prompts.get_all_prompt_files", lambda: {"collision": prompt_seed})
    monkeypatch.setattr("app.bootstrap.knowledge.get_all_knowledge_files", lambda: {"collision": knowledge_seed})
    init_prompts(session)
    init_knowledge(session)
    session.refresh(custom_prompt)
    session.refresh(custom_knowledge)

    assert custom_prompt.built_in is False
    assert custom_prompt.template == "custom template"
    assert custom_prompt.original_template == "custom snapshot"
    assert custom_prompt.is_modified is True
    assert custom_knowledge.built_in is False
    assert custom_knowledge.content == "custom content"
    assert custom_knowledge.original_content == "custom snapshot"
    assert custom_knowledge.is_modified is True


def test_bootstrap_migrates_matching_legacy_items(session, monkeypatch):
    prompt_seed = {"name": "legacy", "description": "seed description", "template": "seed template"}
    knowledge_seed = {"name": "legacy", "description": "seed description", "content": "seed content"}
    prompt = Prompt(name="legacy", description="seed description", template="seed template", built_in=False)
    knowledge = Knowledge(name="legacy", description="seed description", content="seed content", built_in=False)
    session.add_all([prompt, knowledge])
    session.commit()

    monkeypatch.setattr("app.core.config.settings.bootstrap.overwrite", False)
    monkeypatch.setattr("app.bootstrap.prompts.get_all_prompt_files", lambda: {"legacy": prompt_seed})
    monkeypatch.setattr("app.bootstrap.knowledge.get_all_knowledge_files", lambda: {"legacy": knowledge_seed})
    init_prompts(session)
    init_knowledge(session)
    session.refresh(prompt)
    session.refresh(knowledge)

    assert prompt.built_in is True
    assert prompt.original_template == "seed template"
    assert prompt.original_description == "seed description"
    assert knowledge.built_in is True
    assert knowledge.original_content == "seed content"
    assert knowledge.original_description == "seed description"


def test_bootstrap_persists_state_only_changes(session, monkeypatch):
    prompt_seed = {"name": "state-only", "description": "seed description", "template": "seed template"}
    knowledge_seed = {"name": "state-only", "description": "seed description", "content": "seed content"}
    prompt = Prompt(
        name="state-only",
        description="seed description",
        template="seed template",
        original_description="seed description",
        original_template="seed template",
        built_in=True,
        is_modified=True,
    )
    knowledge = Knowledge(
        name="state-only",
        description="seed description",
        content="seed content",
        original_description="seed description",
        original_content="seed content",
        built_in=True,
        is_modified=True,
    )
    session.add_all([prompt, knowledge])
    session.commit()

    monkeypatch.setattr("app.core.config.settings.bootstrap.overwrite", True)
    monkeypatch.setattr("app.bootstrap.prompts.get_all_prompt_files", lambda: {"state-only": prompt_seed})
    monkeypatch.setattr("app.bootstrap.knowledge.get_all_knowledge_files", lambda: {"state-only": knowledge_seed})
    init_prompts(session)
    init_knowledge(session)
    session.expire_all()

    assert session.get(Prompt, prompt.id).is_modified is False
    assert session.get(Knowledge, knowledge.id).is_modified is False


def test_paginated_lists_use_one_stable_result_set(session):
    created_at = datetime(2025, 1, 1, 0, 0, 0)
    session.add(Prompt(name="builtin-p", template="template", built_in=True, created_at=created_at))
    session.add(Knowledge(name="builtin-k", content="content", built_in=True, created_at=created_at))
    for index in range(105):
        session.add(Prompt(name=f"custom-p-{index}", template="template", created_at=created_at))
        session.add(Knowledge(name=f"custom-k-{index}", content="content", created_at=created_at))
    session.commit()

    prompt_page_one = get_prompts(session, skip=0, limit=100)
    prompt_page_two = get_prompts(session, skip=100, limit=100)
    knowledge_service = KnowledgeService(session)
    knowledge_page_one = knowledge_service.list(skip=0, limit=100)
    knowledge_page_two = knowledge_service.list(skip=100, limit=100)
    prompt_api_page_one = prompt_endpoints.read_prompts(session=session, skip=0, limit=100)
    knowledge_api_page_one = knowledge_endpoints.list_knowledge(session=session, skip=0, limit=100)

    assert len(prompt_page_one) <= 100
    assert len(prompt_page_two) <= 100
    assert len(knowledge_page_one) <= 100
    assert len(knowledge_page_two) <= 100
    assert len(prompt_api_page_one.data) <= 100
    assert len(knowledge_api_page_one.data) <= 100
    assert not ({item.id for item in prompt_page_one} & {item.id for item in prompt_page_two})
    assert not ({item.id for item in knowledge_page_one} & {item.id for item in knowledge_page_two})
    assert all(not item.built_in for item in prompt_page_one)
    assert all(not item.built_in for item in knowledge_page_one)
    assert prompt_page_two[-1].built_in is True
    assert knowledge_page_two[-1].built_in is True

    assert len(get_prompts(session)) == 106
    assert len(knowledge_service.list()) == 106
    assert len(prompt_endpoints.read_prompts(session=session, skip=0, limit=None).data) == 106
    assert len(knowledge_endpoints.list_knowledge(session=session, skip=0, limit=None).data) == 106


def test_equal_created_at_uses_id_as_stable_tiebreaker(session):
    created_at = datetime(2025, 1, 1, 0, 0, 0)
    prompts = [Prompt(name=f"p-{index}", template="template", created_at=created_at) for index in range(3)]
    knowledge = [Knowledge(name=f"k-{index}", content="content", created_at=created_at) for index in range(3)]
    session.add_all([*prompts, *knowledge])
    session.commit()

    prompt_ids = {item.id for item in prompts}
    knowledge_ids = {item.id for item in knowledge}
    assert [item.id for item in get_prompts(session)] == sorted(prompt_ids, reverse=True)
    assert [item.id for item in KnowledgeService(session).list()] == sorted(knowledge_ids, reverse=True)


def test_builtin_edit_reset_and_security_boundaries(session):
    prompt = Prompt(
        name="builtin-p",
        description=None,
        template="original",
        original_template="original",
        original_description=None,
        built_in=True,
    )
    knowledge = Knowledge(
        name="builtin-k",
        content="original",
        original_content="original",
        original_description=None,
        built_in=True,
    )
    custom_prompt = Prompt(name="custom-p", template="custom", built_in=False)
    custom_knowledge = Knowledge(name="custom-k", content="custom", built_in=False)
    session.add_all([prompt, knowledge, custom_prompt, custom_knowledge])
    session.commit()

    update_prompt(session, prompt.id, PromptUpdate(description="changed", template="changed"))
    reset_prompt(session, prompt.id)
    service = KnowledgeService(session)
    service.update(knowledge.id, description="changed", content="changed")
    service.reset(knowledge.id)
    session.refresh(prompt)
    session.refresh(knowledge)
    assert prompt.description is None and prompt.is_modified is False
    assert knowledge.original_description is None and knowledge.is_modified is False

    with pytest.raises(ValueError):
        update_prompt(session, prompt.id, PromptUpdate(name="renamed"))
    with pytest.raises(ValueError):
        service.update(knowledge.id, name="renamed")
    with pytest.raises(ValueError):
        reset_prompt(session, custom_prompt.id)
    with pytest.raises(ValueError):
        service.reset(custom_knowledge.id)
    with pytest.raises(ValueError):
        service.delete(knowledge.id)


def test_api_returns_clear_400_errors_for_invalid_operations(session):
    builtin_prompt = Prompt(name="builtin-api", template="template", built_in=True)
    builtin_knowledge = Knowledge(name="builtin-api", content="content", built_in=True)
    missing_snapshot_prompt = Prompt(name="missing-snapshot-p", template="template", built_in=True)
    missing_snapshot_knowledge = Knowledge(name="missing-snapshot-k", content="content", built_in=True)
    session.add_all([builtin_prompt, builtin_knowledge, missing_snapshot_prompt, missing_snapshot_knowledge])
    session.commit()

    with pytest.raises(HTTPException) as prompt_delete_error:
        prompt_endpoints.delete_prompt(session=session, prompt_id=builtin_prompt.id)
    assert prompt_delete_error.value.status_code == 400

    with pytest.raises(HTTPException) as knowledge_delete_error:
        knowledge_endpoints.delete_knowledge(session=session, kid=builtin_knowledge.id)
    assert knowledge_delete_error.value.status_code == 400

    with pytest.raises(HTTPException) as prompt_reset_error:
        prompt_endpoints.reset_prompt_endpoint(session=session, prompt_id=missing_snapshot_prompt.id)
    assert prompt_reset_error.value.status_code == 400
    with pytest.raises(HTTPException) as knowledge_reset_error:
        knowledge_endpoints.reset_knowledge_endpoint(session=session, kid=missing_snapshot_knowledge.id)
    assert knowledge_reset_error.value.status_code == 400

    custom = Prompt(name="duplicate", template="template")
    session.add(custom)
    session.commit()
    with pytest.raises(HTTPException) as duplicate_error:
        prompt_endpoints.create_prompt(session=session, prompt=PromptCreate(name="duplicate", template="template"))
    assert duplicate_error.value.status_code == 400
