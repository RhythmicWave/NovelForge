"""Schema处理工具

用于处理JSON Schema的过滤和转换。
"""

from typing import Any, Dict, List
from copy import deepcopy


def filter_schema_for_ai(schema: Dict[str, Any]) -> Dict[str, Any]:
    """基于元数据的Schema过滤（移除x-ai-exclude=true的字段）
    
    Args:
        schema: JSON Schema对象
        
    Returns:
        过滤后的Schema
    """
    def prune(node: Any, parent_required: List[str] | None = None) -> Any:
        if isinstance(node, dict):
            # 对象：过滤properties中标记了x-ai-exclude的字段
            if node.get('type') == 'object' and isinstance(node.get('properties'), dict):
                props = node.get('properties') or {}
                required = list(node.get('required') or [])
                new_props: Dict[str, Any] = {}
                for name, sch in props.items():
                    if isinstance(sch, dict) and sch.get('x-ai-exclude') is True:
                        # 从required中剔除
                        if name in required:
                            required = [r for r in required if r != name]
                        continue
                    new_props[name] = prune(sch)
                node = dict(node)  # 复制
                node['properties'] = new_props
                if required:
                    node['required'] = required
                elif 'required' in node:
                    # 若全部被剔除，移除required字段
                    node.pop('required', None)
            # 数组：递归处理items/prefixItems（tuple）
            if node.get('type') == 'array':
                if 'items' in node:
                    node = dict(node)
                    node['items'] = prune(node['items'])
                if 'prefixItems' in node and isinstance(node.get('prefixItems'), list):
                    node = dict(node)
                    node['prefixItems'] = [prune(it) for it in node.get('prefixItems', [])]
            # 组合关键字：递归处理anyOf/oneOf/allOf
            for kw in ('anyOf', 'oneOf', 'allOf'):
                if isinstance(node.get(kw), list):
                    node = dict(node)
                    node[kw] = [prune(it) for it in node.get(kw, [])]
            # $defs：仅对内部定义做递归处理（不删除定义键本身）
            if isinstance(node.get('$defs'), dict):
                defs = node.get('$defs') or {}
                new_defs: Dict[str, Any] = {}
                for k, v in defs.items():
                    new_defs[k] = prune(v)
                node = dict(node)
                node['$defs'] = new_defs
            # 清理元数据痕迹（可选，不强制）
            if 'x-ai-exclude' in node:
                node = dict(node)
                node.pop('x-ai-exclude', None)
            return node
        elif isinstance(node, list):
            return [prune(it) for it in node]
        return node

    try:
        root = deepcopy(schema) if isinstance(schema, dict) else {}
        return prune(root)
    except Exception:
        # 出错时不阻断流程，回退原始schema
        return schema
