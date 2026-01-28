"""指令校验工具

负责校验指令的格式、路径、类型和约束。
"""

from typing import Dict, Any, Optional
from pydantic import ValidationError
from loguru import logger



def resolve_schema(schema: Dict[str, Any], root_schema: Dict[str, Any]) -> Dict[str, Any]:
    """解析 Schema 引用 ($ref) 和组合类型 (allOf)
    
    Args:
        schema: 当前 Schema 节点
        root_schema: 根 Schema (包含 $defs/definitions)
        
    Returns:
        解析后的 Schema
    """
    if not isinstance(schema, dict):
        return schema
        
    resolved = schema
    
    # 1. 处理 $ref
    if '$ref' in resolved:
        ref_path = resolved['$ref']
        # 支持 #/$defs/Name 和 #/definitions/Name
        if ref_path.startswith('#/'):
            parts = ref_path.split('/')
            # parts[0] is '#', parts[1] is '$defs' or 'definitions', parts[2] is model name
            if len(parts) >= 3:
                def_section = parts[1]
                model_name = parts[2]
                if def_section in root_schema and model_name in root_schema[def_section]:
                    # 递归解析（处理 Ref -> Ref 的情况）
                    return resolve_schema(root_schema[def_section][model_name], root_schema)
    
    # 2. 处理 allOf (合并属性)
    if 'allOf' in resolved:
        merged = {}
        for sub_schema in resolved['allOf']:
            sub_resolved = resolve_schema(sub_schema, root_schema)
            if isinstance(sub_resolved, dict):
                # 简单合并 properties
                if 'properties' in sub_resolved:
                    if 'properties' not in merged:
                        merged['properties'] = {}
                    merged['properties'].update(sub_resolved['properties'])
                # 合并 required
                if 'required' in sub_resolved:
                    if 'required' not in merged:
                        merged['required'] = []
                    merged['required'].extend(sub_resolved['required'])
                # 合并 type
                if 'type' in sub_resolved and 'type' not in merged:
                    merged['type'] = sub_resolved['type']
        
        # 将当前 schema 的其他属性也合并进去
        for k, v in resolved.items():
            if k != 'allOf':
                if k == 'properties':
                    if 'properties' not in merged:
                        merged['properties'] = {}
                    merged['properties'].update(v)
                elif k == 'required':
                    if 'required' not in merged:
                        merged['required'] = []
                    new_reqs = [r for r in v if r not in merged['required']]
                    merged['required'].extend(new_reqs)
                else:
                    merged[k] = v
        return merged

    return resolved


def get_field_schema_by_path(schema: Dict[str, Any], path: str) -> Optional[Dict[str, Any]]:
    """根据 JSON Pointer 路径获取字段的 Schema
    
    Args:
        schema: 完整的 JSON Schema
        path: JSON Pointer 格式的路径，如 /name 或 /config/theme
        
    Returns:
        字段的 Schema，如果路径不存在则返回 None
    """
    if not path or not path.startswith('/'):
        return None
    
    # 移除开头的 /
    path = path[1:]
    if not path:
        return schema
    
    # 分割路径
    parts = path.split('/')
    current_schema = schema
    
    for part in parts:
        # 每一层都尝试解析引用
        current_schema = resolve_schema(current_schema, schema)
        
        # 处理数组索引（如 hobbies/0）
        if part.isdigit():
            # 数组元素，获取 items schema
            if 'items' in current_schema:
                current_schema = current_schema['items']
            elif 'prefixItems' in current_schema:
                 # 处理 tuple (prefixItems)
                 idx = int(part)
                 if idx < len(current_schema['prefixItems']):
                     current_schema = current_schema['prefixItems'][idx]
                 else:
                     return None
            else:
                # 尝试处理 anyOf/oneOf 中的数组情况
                found_array = False
                for key in ['anyOf', 'oneOf']:
                    if key in current_schema:
                        for option in current_schema[key]:
                            resolved_option = resolve_schema(option, schema)
                            if resolved_option.get('type') == 'array' and 'items' in resolved_option:
                                current_schema = resolved_option['items']
                                found_array = True
                                break
                        if found_array:
                            break
                if not found_array:
                    return None
        else:
            # 对象属性
            # 尝试处理 properties
            if 'properties' in current_schema and part in current_schema['properties']:
                current_schema = current_schema['properties'][part]
            else:
                # 尝试处理 anyOf/oneOf 中的对象情况 (如 Union[A, B])
                # 这是一个简化的处理：只要在任意一个分支中找到该属性，就认为路径从Schema角度是合法的
                # 并返回找到的那个属性的 Schema。
                # 注意：这在校验时可能不够严格（因为不知道运行时是 A 还是 B），
                # 但对于"路径是否存在"的检查，这是合理的宽容策略。
                found_prop = False
                for key in ['anyOf', 'oneOf']:
                    if key in current_schema:
                        for option in current_schema[key]:
                            resolved_option = resolve_schema(option, schema)
                            if 'properties' in resolved_option and part in resolved_option['properties']:
                                current_schema = resolved_option['properties'][part]
                                found_prop = True
                                break
                        if found_prop:
                            break
                
                if not found_prop:
                    return None
    
    # 返回前最后解析一次
    return resolve_schema(current_schema, schema)


def validate_type(value: Any, expected_type: Optional[str]) -> bool:
    """校验值的类型是否匹配
    
    Args:
        value: 要校验的值
        expected_type: 期望的类型（JSON Schema 类型）
        
    Returns:
        是否匹配
    """
    if expected_type is None:
        return True
    
    type_mapping = {
        'string': str,
        'integer': int,
        'number': (int, float),
        'boolean': bool,
        'array': list,
        'object': dict,
        'null': type(None)
    }
    
    expected_python_type = type_mapping.get(expected_type)
    if expected_python_type is None:
        # 未知类型，宽容处理
        return True
    
    return isinstance(value, expected_python_type)


def validate_instruction(instruction: Dict[str, Any], schema: Dict[str, Any]) -> None:
    """校验单条指令的合法性
    
    Args:
        instruction: 指令对象
        schema: 完整的 JSON Schema
        
    Raises:
        ValueError: 校验失败时抛出异常
    """
    op = instruction.get('op')
    
    if op not in ['set', 'append', 'done']:
        raise ValueError(f"未知的指令操作类型: {op}")
    
    if op == 'done':
        # done 指令无需校验
        return
    
    path = instruction.get('path')
    value = instruction.get('value')
    
    if not path:
        raise ValueError("指令缺少 path 字段")
    
    if value is None and op != 'set':
        raise ValueError(f"指令 {op} 缺少 value 字段")
    
    # 1. 路径校验
    field_schema = get_field_schema_by_path(schema, path)
    if not field_schema:
        raise ValueError(f"路径 {path} 不存在于 Schema 中")
    
    # 2. 类型校验
    expected_type = field_schema.get('type')
    
    # 处理 Optional 类型 (anyOf, oneOf)
    # 对于 Optional[List[...]] 类型，schema 可能是 {"anyOf": [{"type": "array", ...}, {"type": "null"}]}
    actual_schema = field_schema
    if 'anyOf' in field_schema:
        # 从 anyOf 中找到数组类型的 schema
        for option in field_schema['anyOf']:
            if option.get('type') == 'array':
                actual_schema = option
                expected_type = 'array'
                break
    elif 'oneOf' in field_schema:
        # 从 oneOf 中找到数组类型的 schema
        for option in field_schema['oneOf']:
            if option.get('type') == 'array':
                actual_schema = option
                expected_type = 'array'
                break
    
    # 对于 append 操作，需要检查数组的 items 类型
    if op == 'append':
        if expected_type != 'array':
            raise ValueError(f"路径 {path} 不是数组类型，无法使用 append 操作")
        
        # 获取数组元素的类型
        items_schema = actual_schema.get('items', {})
        item_type = items_schema.get('type')
        
        if not validate_type(value, item_type):
            raise ValueError(
                f"数组元素类型错误：路径 {path}，期望 {item_type}，实际 {type(value).__name__}"
            )
        
        # 深度校验数组元素结构 (针对 Object 类型)
        if item_type == 'object':
            validate_schema_structure(value, items_schema, schema)

    else:
        # set 操作
        # 对于 Optional 类型，需要检查所有可能的类型
        if 'anyOf' in field_schema or 'oneOf' in field_schema:
            # 尝试匹配任意一个类型
            options = field_schema.get('anyOf', field_schema.get('oneOf', []))
            matched = False
            last_error = None
            
            for option in options:
                resolved_option = resolve_schema(option, schema)
                opt_type = resolved_option.get('type')
                
                # 类型匹配才深入校验
                if validate_type(value, opt_type):
                    try:
                        # 如果是对象，进行结构校验
                        if opt_type == 'object':
                            validate_schema_structure(value, resolved_option, schema)
                        matched = True
                        break
                    except ValueError as e:
                        last_error = e
                        continue
            
            if not matched:
                if last_error:
                    raise last_error
                allowed_types = [resolve_schema(opt, schema).get('type') for opt in options]
                raise ValueError(
                    f"字段类型或结构错误：路径 {path}，期望 {allowed_types} 之一。实际: {type(value).__name__}"
                )
        else:
            # 普通类型校验
            if not validate_type(value, expected_type):
                raise ValueError(
                    f"字段类型错误：路径 {path}，期望 {expected_type}，实际 {type(value).__name__}"
                )
            
            # 如果是对象，进行深度结构校验
            if expected_type == 'object':
                validate_schema_structure(value, actual_schema, schema)

def validate_schema_structure(data: Any, schema_node: Dict[str, Any], root_schema: Dict[str, Any]) -> None:
    """递归校验数据的结构是否符合 Schema 定义 (包含 required 和 properties)
    
    Args:
        data: 要校验的数据
        schema_node: 当前数据的 Schema 节点
        root_schema: 根 Schema (用于解析 $ref)
    
    Raises:
        ValueError: 校验失败
    """
    if not isinstance(data, dict):
        return
        
    resolved = resolve_schema(schema_node, root_schema)
    
    # 1. 遍历 Schema 属性，处理 校验必填 + 注入默认值 + 递归校验
    if 'properties' in resolved:
        properties = resolved['properties']
        required_fields = set(resolved.get('required', []))
        
        # 为了支持注入默认值，我们需要遍历 Schema 的 properties 而不仅仅是 data 的 keys
        # 但要注意：如果 Schema 很大但 Data 很小，这可能有效率问题。
        # 鉴于这是生成过程，通常数据结构不会太大，且为了完整性，遍历 Schema 是合理的。
        
        for field_name, field_schema_ref in properties.items():
            field_schema = resolve_schema(field_schema_ref, root_schema)
            
            # A. 处理缺失字段
            if field_name not in data:
                # 如果有默认值，注入默认值
                if 'default' in field_schema:
                    data[field_name] = field_schema['default']
                # 如果没默认值 且 是必填项，报错
                elif field_name in required_fields:
                    raise ValueError(f"缺少必填字段: {field_name}")
                # 既没默认值也不是必填，跳过
                continue
            
            # B. 处理已存在字段
            field_value = data[field_name]
            
            # 递归校验结构 (如果是对象)
            # 注意：基本类型的 validate_type 已经在 validate_instruction 外层做了一部分，
            # 但这里是递归内部，需要自己负责
            
            # 类型检查
            expected_type = field_schema.get('type')
            if expected_type and not validate_type(field_value, expected_type):
                 # 宽容处理：尝试转换类型? 目前先报错，交给 AI 修复
                 # (后续可以考虑添加自动类型转换逻辑)
                 raise ValueError(f"字段 {field_name} 类型错误: 期望 {expected_type}, 实际 {type(field_value).__name__}")
            
            # 深度递归
            if expected_type == 'object':
                 validate_schema_structure(field_value, field_schema, root_schema)
    
    # 2. (可选) 检查 data 中有多余的字段? (additionalProperties)
    # 目前暂不严格限制，允许 AI 生成额外字段作为"思考备注"或未定义属性


    
    # 3. 约束校验
    # 枚举约束
    if 'enum' in field_schema and value not in field_schema['enum']:
        raise ValueError(
            f"字段 {path} 的值不在枚举范围内：{field_schema['enum']}"
        )
    
    # 数值范围约束
    if expected_type in ['integer', 'number']:
        if 'minimum' in field_schema and value < field_schema['minimum']:
            raise ValueError(
                f"字段 {path} 的值 {value} 小于最小值 {field_schema['minimum']}"
            )
        if 'maximum' in field_schema and value > field_schema['maximum']:
            raise ValueError(
                f"字段 {path} 的值 {value} 大于最大值 {field_schema['maximum']}"
            )
    
    # 字符串长度约束
    if expected_type == 'string':
        if 'minLength' in field_schema and len(value) < field_schema['minLength']:
            raise ValueError(
                f"字段 {path} 的长度 {len(value)} 小于最小长度 {field_schema['minLength']}"
            )
        if 'maxLength' in field_schema and len(value) > field_schema['maxLength']:
            raise ValueError(
                f"字段 {path} 的长度 {len(value)} 大于最大长度 {field_schema['maxLength']}"
            )
    
    # 数组长度约束
    if expected_type == 'array':
        if isinstance(value, list):
            if 'minItems' in field_schema and len(value) < field_schema['minItems']:
                raise ValueError(
                    f"数组 {path} 的长度 {len(value)} 小于最小长度 {field_schema['minItems']}"
                )
            if 'maxItems' in field_schema and len(value) > field_schema['maxItems']:
                raise ValueError(
                    f"数组 {path} 的长度 {len(value)} 大于最大长度 {field_schema['maxItems']}"
                )


def apply_instruction(data: Dict[str, Any], instruction: Dict[str, Any]) -> None:
    """将指令应用到数据对象
    
    Args:
        data: 数据对象（会被修改）
        instruction: 指令对象
    """
    op = instruction.get('op')
    
    if op == 'done':
        return
    
    path = instruction.get('path', '')
    value = instruction.get('value')
    
    # 移除开头的 /
    if path.startswith('/'):
        path = path[1:]
    
    if not path:
        return
    
    # 分割路径
    parts = path.split('/')
    current = data
    
    # 遍历路径，创建中间对象
    for i, part in enumerate(parts[:-1]):
        if part.isdigit():
            # 数组索引
            idx = int(part)
            if not isinstance(current, list):
                logger.warning(f"路径 {path} 中的 {part} 应该是数组索引，但当前对象不是数组")
                return
            
            # 确保数组足够长
            while len(current) <= idx:
                current.append({})
            
            current = current[idx]
        else:
            # 对象属性
            if part not in current:
                # 判断下一个部分是否是数组索引
                next_part = parts[i + 1] if i + 1 < len(parts) else None
                if next_part and next_part.isdigit():
                    current[part] = []
                else:
                    current[part] = {}
            
            current = current[part]
    
    # 设置最后一个字段
    last_part = parts[-1]
    
    if op == 'set':
        if last_part.isdigit():
            idx = int(last_part)
            if isinstance(current, list):
                while len(current) <= idx:
                    current.append(None)
                current[idx] = value
        else:
            current[last_part] = value
    
    elif op == 'append':
        if last_part.isdigit():
            logger.warning(f"append 操作不应该使用数组索引路径: {path}")
            return
        
        # 初始化数组（如果不存在或为 None）
        if last_part not in current or current[last_part] is None:
            current[last_part] = []
        
        if not isinstance(current[last_part], list):
            logger.warning(f"路径 {path} 不是数组，无法执行 append 操作")
            return
        
        current[last_part].append(value)


def format_validation_errors(errors: list) -> str:
    """格式化 Pydantic 验证错误
    
    Args:
        errors: Pydantic 验证错误列表
        
    Returns:
        格式化的错误信息
    """
    lines = []
    for error in errors:
        loc = ' -> '.join(str(l) for l in error.get('loc', []))
        msg = error.get('msg', '未知错误')
        lines.append(f"- {loc}: {msg}")
    
    return '\n'.join(lines)


def extract_error_fields(validation_error: ValidationError) -> list[str]:
    """从 Pydantic 验证错误中提取错误字段列表
    
    Args:
        validation_error: Pydantic 验证错误
        
    Returns:
        错误字段路径列表
    """
    fields = []
    for error in validation_error.errors():
        loc = error.get('loc', ())
        if loc:
            # 转换为 JSON Pointer 格式
            path = '/' + '/'.join(str(l) for l in loc)
            fields.append(path)
    
    return fields


class InstructionExecutor:
    """指令执行器
    
    封装指令的批量执行、验证和数据管理逻辑。
    用于统一 AI 卡片生成和灵感助手工具的指令执行。
    """
    
    def __init__(self, schema: Dict[str, Any], initial_data: Optional[Dict[str, Any]] = None):
        """
        初始化执行器
        
        Args:
            schema: JSON Schema
            initial_data: 初始数据（可选）
        """
        self.schema = schema
        self.data = initial_data.copy() if initial_data else {}
        self.stats = {
            "executed": 0,
            "success": 0,
            "failed": 0
        }
    
    def execute(self, instruction: Dict[str, Any]) -> None:
        """
        执行单条指令
        
        Args:
            instruction: 指令对象
            
        Raises:
            ValueError: 指令校验或执行失败
        """
        self.stats["executed"] += 1
        
        try:
            # 校验指令
            validate_instruction(instruction, self.schema)
            
            # 应用指令
            apply_instruction(self.data, instruction)
            
            self.stats["success"] += 1
            
        except Exception as e:
            self.stats["failed"] += 1
            raise
    
    def execute_batch(self, instructions: list[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量执行指令
        
        Args:
            instructions: 指令数组
            
        Returns:
            执行结果：
            {
                "success": bool - 是否完整成功（所有指令执行且数据完整）
                "data": dict - 当前数据
                "applied": int - 成功执行的指令数
                "failed": int - 失败的指令数
                "errors": list - 失败的指令详情
                "is_complete": bool - 数据是否完整
                "missing_fields": list - 缺失的必填字段
            }
        """
        failed_instructions = []
        
        for idx, inst in enumerate(instructions):
            try:
                self.execute(inst)
            except Exception as e:
                failed_instructions.append({
                    "index": idx,
                    "instruction": inst,
                    "error": str(e)
                })
                logger.warning(f"[InstructionExecutor] 指令执行失败: {e}")
        
        # 验证数据完整性
        is_complete, missing_fields = self.validate_completeness()
        
        return {
            "success": is_complete and len(failed_instructions) == 0,
            "data": self.data,
            "applied": self.stats["success"],
            "failed": self.stats["failed"],
            "errors": failed_instructions,
            "is_complete": is_complete,
            "missing_fields": missing_fields
        }
    
    def validate_completeness(self) -> tuple[bool, list[str]]:
        """
        验证数据完整性
        
        Returns:
            (is_complete, missing_fields):
            - is_complete: 是否完整
            - missing_fields: 缺失的必填字段路径列表
        """
        from app.services.ai.core.model_builder import build_model_from_json_schema
        
        try:
            # 使用 Pydantic 动态模型验证
            DynamicModel = build_model_from_json_schema('ValidationModel', self.schema)
            DynamicModel(**self.data)
            return True, []
        except ValidationError as e:
            # 提取缺失字段
            missing_fields = []
            for error in e.errors():
                if error.get('type') == 'missing':
                    loc = error.get('loc', ())
                    if loc:
                        path = '/' + '/'.join(str(l) for l in loc)
                        missing_fields.append(path)
            
            return False, missing_fields
    
    def get_data(self) -> Dict[str, Any]:
        """获取当前数据"""
        return self.data
    
    def get_stats(self) -> Dict[str, int]:
        """获取执行统计"""
        return self.stats.copy()
