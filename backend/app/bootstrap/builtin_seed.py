from typing import Literal


SeedSyncResult = Literal["builtin", "migrated", "conflict"]


def _set_if_changed(record: object, field_name: str, value: object) -> bool:
    if getattr(record, field_name) == value:
        return False
    setattr(record, field_name, value)
    return True


def sync_builtin_seed(
    record: object,
    *,
    content_field: str,
    original_content_field: str,
    seed_content: str,
    seed_description: str | None,
    overwrite: bool,
) -> tuple[SeedSyncResult, bool]:
    """同步单个种子，避免接管内容不同的同名自定义记录。"""
    description = getattr(record, "description")
    content = getattr(record, content_field)
    is_builtin = bool(getattr(record, "built_in", False))

    if not is_builtin and (content != seed_content or description != seed_description):
        return "conflict", False

    changed = False
    changed |= _set_if_changed(record, "original_description", seed_description)
    changed |= _set_if_changed(record, original_content_field, seed_content)
    changed |= _set_if_changed(record, "built_in", True)

    if overwrite or not is_builtin:
        changed |= _set_if_changed(record, content_field, seed_content)
        changed |= _set_if_changed(record, "description", seed_description)
        changed |= _set_if_changed(record, "is_modified", False)

    return ("migrated" if not is_builtin else "builtin"), changed
