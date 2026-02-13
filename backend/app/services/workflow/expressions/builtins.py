"""表达式执行环境（受控 builtins + helper）"""

from __future__ import annotations

import builtins as py_builtins
from functools import lru_cache
from typing import Any, Callable, Dict

from .functions import get_builtin_functions


ALLOWED_BUILTIN_NAMES = (
    "len",
    "sum",
    "min",
    "max",
    "str",
    "int",
    "float",
    "bool",
    "list",
    "dict",
    "set",
    "tuple",
    "range",
    "enumerate",
    "zip",
    "any",
    "all",
    "abs",
    "round",
    "sorted",
)


@lru_cache(maxsize=1)
def get_safe_builtins() -> Dict[str, Any]:
    """获取安全内置函数白名单"""
    return {
        name: getattr(py_builtins, name)
        for name in ALLOWED_BUILTIN_NAMES
        if hasattr(py_builtins, name)
    }


@lru_cache(maxsize=1)
def get_safe_helpers() -> Dict[str, Callable]:
    """获取表达式 helper（兼容历史函数库）"""
    return get_builtin_functions()


@lru_cache(maxsize=1)
def get_safe_globals() -> Dict[str, Any]:
    """构造 eval 全局变量"""
    safe_builtins = get_safe_builtins()
    safe_helpers = get_safe_helpers()
    globals_dict: Dict[str, Any] = {
        "__builtins__": safe_builtins
    }

    # helper 与 builtins 同名时，以 builtins 为准
    for name, func in safe_helpers.items():
        if name not in safe_builtins:
            globals_dict[name] = func

    return globals_dict


@lru_cache(maxsize=1)
def get_safe_global_names() -> set[str]:
    """获取全局可见名字（用于依赖提取过滤）"""
    names = set(get_safe_builtins().keys())
    names.update(get_safe_helpers().keys())
    return names

