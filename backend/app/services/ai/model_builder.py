"""动态模型构建服务

负责从 JSON Schema 动态构建 Pydantic 模型。
"""

from typing import Dict, Any, List, Type
from pydantic import create_model, Field as PydanticField, BaseModel
from typing import Any as _Any, Dict as _Dict, List as _List


def json_schema_to_py_type(sch: Dict[str, Any]) -> Any:
    """将 JSON Schema 类型转换为 Python 类型注解
    
    Args:
        sch: JSON Schema 定义
        
    Returns:
        Python 类型注解
    """
    if not isinstance(sch, dict):
        return _Any
    
    # 处理 $ref
    if '$ref' in sch:
        # 简化处理：引用统一按对象处理
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
        return _List[json_schema_to_py_type(item_sch)]  # type: ignore[index]
    if t == 'object':
        # 若有 properties 但为动态结构，这里按 Dict 处理
        return _Dict[str, _Any]
    
    # 未声明 type 或无法识别
    return _Any


def build_model_from_json_schema(model_name: str, schema: Dict[str, Any]) -> Type[BaseModel]:
    """从 JSON Schema 动态构建 Pydantic 模型
    
    Args:
        model_name: 模型名称
        schema: JSON Schema 定义
        
    Returns:
        动态创建的 Pydantic 模型类
    """
    props: Dict[str, Any] = (schema or {}).get('properties') or {}
    required: List[str] = list((schema or {}).get('required') or [])
    field_defs: Dict[str, tuple] = {}
    
    for fname, fsch in props.items():
        # 获取类型注解
        anno = json_schema_to_py_type(fsch if isinstance(fsch, dict) else {})
        
        # 获取描述
        desc = fsch.get('description') if isinstance(fsch, dict) else None
        
        # 判断是否必填
        is_required = fname in required
        
        # 构建字段定义
        if desc is not None:
            default_val = PydanticField(... if is_required else None, description=desc)
        else:
            default_val = ... if is_required else None
        
        field_defs[fname] = (anno, default_val)
    
    return create_model(model_name, **field_defs)
