"""提示词初始化。

从文件系统加载提示词模板并同步到数据库。
"""

import os

from loguru import logger
from sqlmodel import Session, select

from app.core.config import settings
from app.db.models import Prompt
from .builtin_seed import sync_builtin_seed
from .registry import initializer


def _parse_prompt_file(file_path: str) -> dict:
    """解析单个提示词文件。"""
    with open(file_path, "r", encoding="utf-8") as file:
        content = file.read()

    filename = os.path.basename(file_path)
    name = os.path.splitext(filename)[0]
    return {
        "name": name,
        "description": f"AI任务提示词: {name}",
        "template": content.strip(),
    }


def get_all_prompt_files() -> dict:
    """从文件系统加载所有提示词种子，按名称返回。"""
    prompt_dir = os.path.join(os.path.dirname(__file__), "prompts")
    if not os.path.exists(prompt_dir):
        logger.warning(f"未找到提示词目录 {prompt_dir}，无法加载提示词。")
        return {}

    prompt_files = {}
    for filename in os.listdir(prompt_dir):
        if filename.endswith((".prompt", ".txt")):
            file_path = os.path.join(prompt_dir, filename)
            name = os.path.splitext(filename)[0]
            prompt_files[name] = _parse_prompt_file(file_path)
    return prompt_files


@initializer(name="提示词", order=10)
def init_prompts(session: Session) -> None:
    """同步内置提示词种子并保留用户对内置项的修改。"""
    overwrite = settings.bootstrap.should_overwrite
    existing_prompts = {prompt.name: prompt for prompt in session.exec(select(Prompt)).all()}
    state_changed = False
    created = 0
    updated = 0
    migrated = 0
    conflicts = 0
    prompts_to_add = []

    for prompt_name, prompt_data in get_all_prompt_files().items():
        existing_prompt = existing_prompts.get(prompt_name)
        if existing_prompt is None:
            prompts_to_add.append(
                Prompt(
                    **prompt_data,
                    built_in=True,
                    original_template=prompt_data["template"],
                    original_description=prompt_data.get("description"),
                )
            )
            created += 1
            state_changed = True
            continue

        result, changed = sync_builtin_seed(
            existing_prompt,
            content_field="template",
            original_content_field="original_template",
            seed_content=prompt_data["template"],
            seed_description=prompt_data.get("description"),
            overwrite=overwrite,
        )
        state_changed |= changed
        if result == "conflict":
            conflicts += 1
            logger.warning(
                "提示词种子与同名自定义项冲突，保留自定义项：{}",
                prompt_name,
            )
        elif result == "migrated":
            migrated += 1
        elif overwrite and changed:
            updated += 1

    if prompts_to_add:
        session.add_all(prompts_to_add)

    if state_changed:
        session.commit()
        logger.info(
            "提示词初始化完成：新增 {}，覆盖更新 {}，兼容迁移 {}，冲突 {}（overwrite={}）",
            created,
            updated,
            migrated,
            conflicts,
            overwrite,
        )
    else:
        logger.info("提示词种子无需更新（overwrite={}）", overwrite)
