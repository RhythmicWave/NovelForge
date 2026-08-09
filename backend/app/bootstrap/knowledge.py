"""知识库初始化。

从文件系统加载知识库内容并同步到数据库。
"""

import os

from loguru import logger
from sqlmodel import Session, select

from app.core.config import settings
from app.db.models import Knowledge
from .builtin_seed import sync_builtin_seed
from .registry import initializer


def get_all_knowledge_files() -> dict:
    """从文件系统加载知识库种子，按名称返回。"""
    knowledge_dir = os.path.join(os.path.dirname(__file__), "knowledge")
    if not os.path.exists(knowledge_dir):
        logger.warning("未找到知识库目录 {}，无法加载知识库。", knowledge_dir)
        return {}

    knowledge_files = {}
    for filename in os.listdir(knowledge_dir):
        if not filename.lower().endswith((".txt", ".md")):
            continue
        file_path = os.path.join(knowledge_dir, filename)
        name = os.path.splitext(filename)[0]
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                content = file.read().strip()
        except OSError as exc:
            logger.warning("读取知识库种子文件失败 {}：{}", file_path, exc)
            continue
        knowledge_files[name] = {
            "name": name,
            "description": f"预置知识库：{name}",
            "content": content,
        }
    return knowledge_files


@initializer(name="知识库", order=30)
def init_knowledge(session: Session) -> None:
    """同步内置知识库种子并保留用户对内置项的修改。"""
    overwrite = settings.bootstrap.should_overwrite
    existing = {item.name: item for item in session.exec(select(Knowledge)).all()}
    knowledge_to_add = []
    state_changed = False
    created = 0
    updated = 0
    migrated = 0
    conflicts = 0

    for name, seed in get_all_knowledge_files().items():
        existing_item = existing.get(name)
        if existing_item is None:
            knowledge_to_add.append(
                Knowledge(
                    **seed,
                    built_in=True,
                    original_content=seed["content"],
                    original_description=seed["description"],
                )
            )
            created += 1
            state_changed = True
            continue

        result, changed = sync_builtin_seed(
            existing_item,
            content_field="content",
            original_content_field="original_content",
            seed_content=seed["content"],
            seed_description=seed["description"],
            overwrite=overwrite,
        )
        state_changed |= changed
        if result == "conflict":
            conflicts += 1
            logger.warning(
                "知识库种子与同名自定义项冲突，保留自定义项：{}",
                name,
            )
        elif result == "migrated":
            migrated += 1
        elif overwrite and changed:
            updated += 1

    if knowledge_to_add:
        session.add_all(knowledge_to_add)

    if state_changed:
        session.commit()
        logger.info(
            "知识库初始化完成：新增 {}，覆盖更新 {}，兼容迁移 {}，冲突 {}（overwrite={}）",
            created,
            updated,
            migrated,
            conflicts,
            overwrite,
        )
    else:
        logger.info("知识库种子无需更新（overwrite={}）", overwrite)
