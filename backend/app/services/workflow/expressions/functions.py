"""表达式内置函数库"""

import re
import json
import uuid
from typing import Any, Dict, Callable, List, Optional
from datetime import datetime, timedelta


# 函数注册表
_FUNCTION_REGISTRY: Dict[str, Callable] = {}


def register_function(name: str):
    """注册内置函数的装饰器"""
    def decorator(func: Callable):
        _FUNCTION_REGISTRY[name] = func
        return func
    return decorator


def get_builtin_functions() -> Dict[str, Callable]:
    """获取所有内置函数"""
    return _FUNCTION_REGISTRY.copy()


# ==================== 字符串函数 ====================

@register_function("len")
def fn_len(obj: Any) -> int:
    """获取长度"""
    return len(obj)


@register_function("str")
def fn_str(obj: Any) -> str:
    """转换为字符串"""
    return str(obj)


@register_function("upper")
def fn_upper(s: str) -> str:
    """转换为大写"""
    return s.upper()


@register_function("lower")
def fn_lower(s: str) -> str:
    """转换为小写"""
    return s.lower()


@register_function("strip")
def fn_strip(s: str, chars: Optional[str] = None) -> str:
    """去除首尾空白"""
    return s.strip(chars)


@register_function("split")
def fn_split(s: str, sep: Optional[str] = None, maxsplit: int = -1) -> List[str]:
    """分割字符串"""
    return s.split(sep, maxsplit)


@register_function("join")
def fn_join(sep: str, iterable: List[str]) -> str:
    """连接字符串"""
    return sep.join(iterable)


@register_function("replace")
def fn_replace(s: str, old: str, new: str, count: int = -1) -> str:
    """替换字符串"""
    return s.replace(old, new, count)


@register_function("startswith")
def fn_startswith(s: str, prefix: str) -> bool:
    """检查是否以指定前缀开始"""
    return s.startswith(prefix)


@register_function("endswith")
def fn_endswith(s: str, suffix: str) -> bool:
    """检查是否以指定后缀结束"""
    return s.endswith(suffix)


@register_function("contains")
def fn_contains(s: str, substring: str) -> bool:
    """检查是否包含子字符串"""
    return substring in s


@register_function("format")
def fn_format(template: str, *args, **kwargs) -> str:
    """格式化字符串"""
    return template.format(*args, **kwargs)


@register_function("regex_match")
def fn_regex_match(pattern: str, text: str) -> bool:
    """正则匹配"""
    return bool(re.search(pattern, text))


@register_function("regex_replace")
def fn_regex_replace(pattern: str, repl: str, text: str) -> str:
    """正则替换"""
    return re.sub(pattern, repl, text)


# ==================== 数值函数 ====================

@register_function("int")
def fn_int(obj: Any) -> int:
    """转换为整数"""
    return int(obj)


@register_function("float")
def fn_float(obj: Any) -> float:
    """转换为浮点数"""
    return float(obj)


@register_function("abs")
def fn_abs(x: float) -> float:
    """绝对值"""
    return abs(x)


@register_function("round")
def fn_round(x: float, ndigits: int = 0) -> float:
    """四舍五入"""
    return round(x, ndigits)


@register_function("min")
def fn_min(*args) -> Any:
    """最小值"""
    return min(args)


@register_function("max")
def fn_max(*args) -> Any:
    """最大值"""
    return max(args)


@register_function("sum")
def fn_sum(iterable: List[float]) -> float:
    """求和"""
    return sum(iterable)


# ==================== 列表/字典函数 ====================

@register_function("list")
def fn_list(obj: Any) -> List:
    """转换为列表"""
    return list(obj)


@register_function("dict")
def fn_dict(**kwargs) -> Dict:
    """创建字典"""
    return kwargs


@register_function("keys")
def fn_keys(d: Dict) -> List:
    """获取字典键"""
    return list(d.keys())


@register_function("values")
def fn_values(d: Dict) -> List:
    """获取字典值"""
    return list(d.values())


@register_function("items")
def fn_items(d: Dict) -> List:
    """获取字典项"""
    return list(d.items())


@register_function("get")
def fn_get(d: Dict, key: str, default: Any = None) -> Any:
    """安全获取字典值"""
    return d.get(key, default)


@register_function("filter")
def fn_filter(predicate: str, iterable: List) -> List:
    """过滤列表（简化版）"""
    # 注意：这里的predicate是字符串，需要特殊处理
    # 实际使用中应该通过evaluator处理
    return [item for item in iterable if item]


@register_function("map")
def fn_map(func_name: str, iterable: List) -> List:
    """映射列表（简化版）"""
    # 注意：这里的func_name是字符串，需要特殊处理
    return list(iterable)


@register_function("sort")
def fn_sort(iterable: List, reverse: bool = False) -> List:
    """排序列表"""
    return sorted(iterable, reverse=reverse)


@register_function("reverse")
def fn_reverse(iterable: List) -> List:
    """反转列表"""
    return list(reversed(iterable))


@register_function("unique")
def fn_unique(iterable: List) -> List:
    """去重"""
    seen = set()
    result = []
    for item in iterable:
        # 处理不可哈希的类型
        try:
            if item not in seen:
                seen.add(item)
                result.append(item)
        except TypeError:
            if item not in result:
                result.append(item)
    return result


@register_function("flatten")
def fn_flatten(iterable: List) -> List:
    """展平列表"""
    result = []
    for item in iterable:
        if isinstance(item, list):
            result.extend(fn_flatten(item))
        else:
            result.append(item)
    return result


# ==================== 日期时间函数 ====================

@register_function("now")
def fn_now() -> str:
    """当前时间（ISO格式）"""
    return datetime.now().isoformat()


@register_function("today")
def fn_today() -> str:
    """今天日期"""
    return datetime.now().date().isoformat()


@register_function("format_date")
def fn_format_date(date_str: str, format: str = "%Y-%m-%d") -> str:
    """格式化日期"""
    dt = datetime.fromisoformat(date_str)
    return dt.strftime(format)


@register_function("parse_date")
def fn_parse_date(date_str: str, format: str = "%Y-%m-%d") -> str:
    """解析日期"""
    dt = datetime.strptime(date_str, format)
    return dt.isoformat()


@register_function("add_days")
def fn_add_days(date_str: str, days: int) -> str:
    """日期加天数"""
    dt = datetime.fromisoformat(date_str)
    new_dt = dt + timedelta(days=days)
    return new_dt.isoformat()


# ==================== JSON函数 ====================

@register_function("json_parse")
def fn_json_parse(json_str: str) -> Any:
    """解析JSON"""
    return json.loads(json_str)


@register_function("json_stringify")
def fn_json_stringify(obj: Any, indent: Optional[int] = None) -> str:
    """序列化为JSON"""
    return json.dumps(obj, indent=indent, ensure_ascii=False)


# ==================== 工具函数 ====================

@register_function("uuid")
def fn_uuid() -> str:
    """生成UUID"""
    return str(uuid.uuid4())


@register_function("bool")
def fn_bool(obj: Any) -> bool:
    """转换为布尔值"""
    return bool(obj)


@register_function("type")
def fn_type(obj: Any) -> str:
    """获取类型名称"""
    return type(obj).__name__


@register_function("range")
def fn_range(start: int, stop: Optional[int] = None, step: int = 1) -> List[int]:
    """生成范围"""
    if stop is None:
        return list(range(start))
    return list(range(start, stop, step))


@register_function("enumerate")
def fn_enumerate(iterable: List, start: int = 0) -> List[tuple]:
    """枚举"""
    return list(enumerate(iterable, start))


@register_function("zip")
def fn_zip(*iterables) -> List[tuple]:
    """压缩"""
    return list(zip(*iterables))


@register_function("all")
def fn_all(iterable: List) -> bool:
    """全部为真"""
    return all(iterable)


@register_function("any")
def fn_any(iterable: List) -> bool:
    """任一为真"""
    return any(iterable)


@register_function("default")
def fn_default(value: Any, default_value: Any) -> Any:
    """提供默认值"""
    return value if value is not None else default_value


@register_function("coalesce")
def fn_coalesce(*values) -> Any:
    """返回第一个非None值"""
    for value in values:
        if value is not None:
            return value
    return None
