"""XML 工作流变量重命名工具

支持重命名变量并自动更新所有引用。
"""

import re
from typing import Set
from loguru import logger


def rename_variable(code: str, old_name: str, new_name: str) -> str:
    """重命名变量并更新所有引用
    
    Args:
        code: 工作流代码
        old_name: 旧变量名
        new_name: 新变量名
        
    Returns:
        更新后的代码
        
    Raises:
        ValueError: 参数错误或重命名失败
    """
    # 验证参数
    if not old_name or not new_name:
        raise ValueError("变量名不能为空")
    
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', old_name):
        raise ValueError(f"旧变量名格式错误: {old_name}")
    
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', new_name):
        raise ValueError(f"新变量名格式错误: {new_name}")
    
    if old_name == new_name:
        return code
    
    logger.info(f"[Renamer] 重命名变量: {old_name} -> {new_name}")
    
    # 1. 更新节点定义中的 name 属性
    code = _update_node_name_attribute(code, old_name, new_name)
    
    # 2. 更新节点内部的变量定义
    code = _update_variable_definition(code, old_name, new_name)
    
    # 3. 更新所有变量引用
    code = _update_variable_references(code, old_name, new_name)
    
    logger.debug(f"[Renamer] 重命名完成")
    return code


def _update_node_name_attribute(code: str, old_name: str, new_name: str) -> str:
    """更新 <node name="..."> 标签中的 name 属性
    
    Args:
        code: 工作流代码
        old_name: 旧变量名
        new_name: 新变量名
        
    Returns:
        更新后的代码
    """
    # 匹配 <node name="old_name" ...>
    pattern = rf'(<node\s+[^>]*name=")({re.escape(old_name)})(")'
    
    def replace_name(match):
        return match.group(1) + new_name + match.group(3)
    
    return re.sub(pattern, replace_name, code)


def _update_variable_definition(code: str, old_name: str, new_name: str) -> str:
    """更新节点内部的变量定义
    
    新格式中节点内部不包含变量赋值，所以这个函数不需要做任何事情。
    保留此函数是为了保持接口一致性。
    
    Args:
        code: 工作流代码
        old_name: 旧变量名
        new_name: 新变量名
        
    Returns:
        原样返回代码
    """
    # 新格式中不需要更新节点内部的变量定义
    return code


def _update_variable_references(code: str, old_name: str, new_name: str) -> str:
    """更新所有变量引用
    
    包括：
    - 简单引用：old_name
    - 属性访问：old_name.field
    - 下标访问：old_name[key]
    - 方法调用：old_name.method()
    
    Args:
        code: 工作流代码
        old_name: 旧变量名
        new_name: 新变量名
        
    Returns:
        更新后的代码
    """
    # 使用单词边界 \b 确保只匹配完整的变量名
    # 例如：old_name 会被替换，但 old_name_2 不会
    pattern = rf'\b{re.escape(old_name)}\b'
    
    return re.sub(pattern, new_name, code)


def validate_rename(code: str, old_name: str, new_name: str) -> bool:
    """验证重命名是否安全
    
    检查：
    1. 旧变量名是否存在
    2. 新变量名是否已被使用
    
    Args:
        code: 工作流代码
        old_name: 旧变量名
        new_name: 新变量名
        
    Returns:
        是否可以安全重命名
    """
    # 提取所有节点的 name 属性
    node_names = set(re.findall(r'<node\s+[^>]*name="([^"]+)"', code))
    
    # 检查旧变量名是否存在
    if old_name not in node_names:
        logger.warning(f"[Renamer] 旧变量名不存在: {old_name}")
        return False
    
    # 检查新变量名是否已被使用
    if new_name in node_names and new_name != old_name:
        logger.warning(f"[Renamer] 新变量名已存在: {new_name}")
        return False
    
    return True
