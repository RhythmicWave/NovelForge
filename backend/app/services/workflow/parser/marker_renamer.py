"""工作流变量重命名工具（注释标记 DSL）。"""

import re

from loguru import logger


def rename_variable(code: str, old_name: str, new_name: str) -> str:
    """重命名变量并更新所有引用。"""
    if not old_name or not new_name:
        raise ValueError("变量名不能为空")

    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", old_name):
        raise ValueError(f"旧变量名格式错误: {old_name}")

    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", new_name):
        raise ValueError(f"新变量名格式错误: {new_name}")

    if old_name == new_name:
        return code

    logger.info(f"[Renamer] 重命名变量: {old_name} -> {new_name}")

    code = _update_node_name_meta(code, old_name, new_name)
    code = _update_variable_definition(code, old_name, new_name)
    code = _update_variable_references(code, old_name, new_name)

    logger.debug("[Renamer] 重命名完成")
    return code


def _update_node_name_meta(code: str, old_name: str, new_name: str) -> str:
    """更新 #@node(name=...) 元数据中的变量名。"""
    marker_double = rf'(#@node\([^\n]*\bname\s*=\s*")({re.escape(old_name)})(")'
    marker_single = rf"(#@node\([^\n]*\bname\s*=\s*')({re.escape(old_name)})(')"
    marker_bare = rf'(#@node\([^\n]*\bname\s*=\s*)({re.escape(old_name)})(?=[,\)])'

    code = re.sub(marker_double, lambda m: m.group(1) + new_name + m.group(3), code)
    code = re.sub(marker_single, lambda m: m.group(1) + new_name + m.group(3), code)
    code = re.sub(marker_bare, lambda m: m.group(1) + new_name, code)
    return code


def _update_variable_definition(code: str, old_name: str, new_name: str) -> str:
    """更新 Python 赋值左侧变量名。"""
    pattern = rf"(^\s*){re.escape(old_name)}(\s*=)"
    return re.sub(pattern, rf"\1{new_name}\2", code, flags=re.MULTILINE)


def _update_variable_references(code: str, old_name: str, new_name: str) -> str:
    """更新所有变量引用。"""
    pattern = rf"\b{re.escape(old_name)}\b"
    return re.sub(pattern, new_name, code)


def validate_rename(code: str, old_name: str, new_name: str) -> bool:
    """验证重命名是否安全。"""
    node_names = set()

    node_names.update(re.findall(r"#@node\([^\n]*\bname\s*=\s*\"([^\"]+)\"", code))
    node_names.update(re.findall(r"#@node\([^\n]*\bname\s*=\s*'([^']+)'", code))

    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*=", stripped)
        if match:
            node_names.add(match.group(1))

    if old_name not in node_names:
        logger.warning(f"[Renamer] 旧变量名不存在: {old_name}")
        return False

    if new_name in node_names and new_name != old_name:
        logger.warning(f"[Renamer] 新变量名已存在: {new_name}")
        return False

    return True

