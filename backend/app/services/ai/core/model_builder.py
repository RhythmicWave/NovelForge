"""动态模型构建服务

负责从 JSON Schema 动态构建 Pydantic 模型。
"""

from typing import Dict, Any, List, Type
from pydantic import create_model, Field as PydanticField, BaseModel
from typing import Any as _Any, Dict as _Dict, List as _List


def json_schema_to_py_type(sch: Dict[str, Any], schema_root: Dict[str, Any] = None) -> Any:
    """将 JSON Schema 类型转换为 Python 类型注解
    
    Args:
        sch: JSON Schema 定义
        schema_root: 根 Schema (用于解析 $ref)
        
    Returns:
        Python 类型注解或 Pydantic 模型类
    """
    if not isinstance(sch, dict):
        return _Any
    
    # 处理 $ref
    if '$ref' in sch:
        ref_path = sch['$ref']
        # 简单的 $ref 解析: #/$defs/ModelName
        if ref_path.startswith('#/$defs/') and schema_root and '$defs' in schema_root:
            def_name = ref_path.split('/')[-1]
            ref_schema = schema_root['$defs'].get(def_name)
            if ref_schema:
                # 递归构建引用的模型
                # 使用引用名作为模型名，避免哈希命名
                return build_model_from_json_schema(def_name, ref_schema, schema_root)
        
        # 解析失败或无 definitions，回退到 Dict
        return _Dict[str, _Any]
    
    t = sch.get('type')
    
    if t == 'string':
        return str
    if t == 'integer':
        return int
    if t == 'number':
        return float
    if t == 'boolean':
        return bool
    if t == 'array':
        item_sch = sch.get('items') or {}
        return _List[json_schema_to_py_type(item_sch, schema_root)]  # type: ignore[index]
    if t == 'object':
        # **关键修复**: 如果有 properties,递归构建嵌套 Pydantic 模型
        if 'properties' in sch:
            # 生成唯一的嵌套模型名
            import hashlib
            schema_str = str(sorted(sch.get('properties', {}).keys()))
            model_hash = hashlib.md5(schema_str.encode()).hexdigest()[:8]
            nested_model_name = f'NestedModel_{model_hash}'
            return build_model_from_json_schema(nested_model_name, sch, schema_root)
        else:
            # 没有 properties 的对象,按 Dict 处理
            return _Dict[str, _Any]
    
    # 未声明 type 或无法识别
    return _Any


def build_model_from_json_schema(model_name: str, schema: Dict[str, Any], root_schema: Dict[str, Any] = None) -> Type[BaseModel]:
    """从 JSON Schema 动态构建 Pydantic 模型
    
    Args:
        model_name: 模型名称
        schema: JSON Schema 定义
        root_schema: 根 Schema (用于解析 $ref)，默认为 schema 自己
        
    Returns:
        动态创建的 Pydantic 模型类
    """
    if root_schema is None:
        root_schema = schema

    # 1. 如果当前 schema 本身就是一个 $ref，直接解析并返回引用模型
    if '$ref' in schema:
         return json_schema_to_py_type(schema, root_schema)

    props: Dict[str, Any] = (schema or {}).get('properties') or {}
    required: List[str] = list((schema or {}).get('required') or [])
    field_defs: Dict[str, tuple] = {}
    
    for fname, fsch in props.items():
        # 获取类型注解 (可能是嵌套模型)
        # 传入 root_schema 以便在深层嵌套中仍能找到 definitions
        anno = json_schema_to_py_type(fsch if isinstance(fsch, dict) else {}, root_schema)
        
        # 获取描述
        desc = fsch.get('description') if isinstance(fsch, dict) else None
        
        # 判断是否必填
        is_required = fname in required
        
        # 构建字段定义：必填用 ...，非必填用 None
        if desc is not None:
            default_val = PydanticField(... if is_required else None, description=desc)
        else:
            default_val = ... if is_required else None
        
        field_defs[fname] = (anno, default_val)
    
    return create_model(model_name, **field_defs)

